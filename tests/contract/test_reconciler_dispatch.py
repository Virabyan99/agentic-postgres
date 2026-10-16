"""The reconciler's half that runs commands: `project.create`, step by step (ADR 0256).

OPN-DISPATCH-001 (D2154, D2173, D2153, D2179, D2160). `bin/reconciler.py` is
loaded as a module and its two outward edges are replaced by recorders that
answer from a script and keep every call -- `subprocess.run` (the `bin/`
commands an operation runs) and `container_exec.run` (the control database and
the project's) -- the pattern of `test_control_command.py` (D2115), so a proof
can say what WAS and was NOT run, with which argv, environment and stdin.

The slot is files in a directory the proof owns, prepared the way `bin/slot.sh
prepare` and the provisioning sheet leave it; its DNS reading is the
recorder's. `read_deployed_document` is replaced by a stand-in that returns
what the fake deploy wrote. What the control set does with each call is
`test_reconciler_claim.py`'s; the handoff against a real project cluster is
`test_admin_handoff.py`'s.
"""

from __future__ import annotations

import ast
import configparser
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    branch_record,
    host_config,
    operations,
    reconciler_dispatch,
    slot,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

HOST = REPO_ROOT / "host.example.yaml"
KEY = "slot1-dev"
OPERATION = "6f1c2a4e-1b7d-4d0e-9a51-0c3f8e2d7b10"
ORG = "0b5c6f0e-8d0e-4c3a-9a4e-3f1d2b7c9e11"
REQUESTER = "2d4a6c8e-0f1b-4d3e-8a5c-7e9f1b3d5a70"
ADMIN_ID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
RESET_ID = "1f2e3d4c-5b6a-4978-8a1b-2c3d4e5f6a7b"
INSTANCE = "3c1d9e7a-2b4f-4c6d-8e0a-5b7c9d1e3f5a"
PRINTED = "77777777-7777-4777-8777-777777777777"
OWNER = (1000, 1000)
HEAD = "a" * 40
CONTROL = ("apg-control-prod-postgres-1", "control_prod")
#: The customer's display name and the handoff hash: neither may reach an argv.
NAME = "Zebra Crossing 7"
HANDOFF = hashlib.sha256(b"the requester's token").hexdigest()
ARGUMENTS = {
    "name": NAME,
    "profile": "standard",
    "admin_username": "ada.admin",
    "handoff_sha256": HANDOFF,
}
ADMISSION_REASON = "the host has 412 MiB left and the candidate charges 840"
#: Admission's own lines (D2362): what `admit.sh --json` prints its decision on.
REQUESTED_MB = 840
SAFE_REFUSED_MB = 412
SAFE_ADMITTED_MB = 4600
#: Session 39 (ADR 0269): the doors a slot's document records, and a verifier
#: shaped as PostgreSQL stores one -- never a password.
POOL_USER = "slot1_dev_customer_app"
DIRECT_USER = "slot1_dev_customer_admin"
VERIFIER = (
    "SCRAM-SHA-256$4096:c2FsdHNhbHRzYWx0c2FsdA==$"
    "U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmU=:"
    "U2VydmVyS2V5U2VydmVyS2V5U2VydmVyS2V5U2VydmU="
)
DOORS = {
    "enabled": True,
    "pooled": {
        "host": "pool.slot1.example.test", "port": 5432, "user": POOL_USER,
        "database": "slot1_dev", "sslmode": "verify-full", "connection_limit": 2,
    },
    "direct": {
        "host": "direct.slot1.example.test", "port": 5432, "user": DIRECT_USER,
        "database": "slot1_dev", "sslmode": "verify-full", "connection_limit": 2,
    },
}  # fmt: skip
#: What the fake storage container prints, and the archive the fake pg_dump writes.
URL = "https://r2.example.test/bucket/apg/exports/x.dump?X-Amz-Expires=900&X-Amz-Signature=5ec"
ARCHIVE = b"PGDMP\x01 the customer's schemas"
STORAGE = "apg-slot1-dev-storage-1"
#: Session 40: a branch's arguments, and the point a branch at the end reached.
BRANCH_ARGUMENTS = {"branch": "dev", "app_verifier": VERIFIER, "admin_verifier": VERIFIER}
BRANCH_REACHED = "2026-10-14T09:31:07Z"
POINT = "2026-10-14T09:30:00Z"
EXPIRES = "2026-10-14T12:00:00Z"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_reconciler", REPO_ROOT / "bin" / "reconciler.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**changes: Any) -> dict[str, Any]:
    row = {
        "id": OPERATION,
        "organization_id": ORG,
        "project_key": None,
        "type": "project.create",
        "arguments": dict(ARGUMENTS),
        "attempt": 1,
        "requested_by": REQUESTER,
    }
    row.update(changes)
    return row


def _variables(text: str) -> dict[str, str]:
    """What `psql_input` set, unescaped as psql unescapes it."""
    found = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\\set ([a-z_]+) '(.*)'", line)
        if not match:
            continue
        raw, value, index = match.group(2), [], 0
        while index < len(raw):
            char = raw[index]
            if char == "\\":
                value.append({"n": "\n", "r": "\r"}.get(raw[index + 1], raw[index + 1]))
                index += 2
            elif char == "'":
                value.append("'")
                index += 2
            else:
                value.append(char)
                index += 1
        found[match.group(1)] = "".join(value)
    return found


class Database:
    """`container_exec.run`'s stand-in: answers each statement from a script."""

    def __init__(self, claims: list[dict[str, Any]]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.claims = list(claims)
        self.interrupted: list[dict[str, Any]] = []
        self.uploaded: bytes | None = None
        self.upload_code = 0
        #: A statement containing this marker is refused, as psql refuses one.
        self.refuse: str | None = None

    def __call__(self, container: str, *argv: str, **kwargs: Any) -> Any:
        if argv and argv[0] == "pg_dump":
            self.calls.append({"container": container, "argv": list(argv), "input": "", "vars": {}})
            return subprocess.CompletedProcess(argv, 0, ARCHIVE, b"")
        if "app.export_upload" in argv:
            self.uploaded = kwargs.get("input")
            self.calls.append({"container": container, "argv": list(argv), "input": "", "vars": {}})
            return subprocess.CompletedProcess(argv, self.upload_code, (URL + "\n").encode(), b"")
        text = kwargs.get("input") or ""
        self.calls.append(
            {"container": container, "argv": list(argv), "input": text, "vars": _variables(text)}
        )
        if self.refuse is not None and self.refuse in text:
            return subprocess.CompletedProcess(argv, 1, "", "ERROR:  refused by the rig\n")
        answers = (
            (
                "control_claim_operation",
                lambda: json.dumps(self.claims.pop(0)) if self.claims else "",
            ),
            ("control_interrupted_operations", lambda: json.dumps(self.interrupted)),
            ("control_record_slots", lambda: "1"),
            ("control_adopt_project", lambda: KEY),
            ("control_mark_deleted", lambda: "t"),
            ("FROM app_private.users", lambda: ADMIN_ID),
            ("auth_open_password_reset", lambda: RESET_ID),
            ("project_identity", lambda: INSTANCE),
        )
        out = next((answer() for marker, answer in answers if marker in text), "")
        return subprocess.CompletedProcess(argv, 0, out + "\n", "")

    def named(self, function: str) -> list[dict[str, str]]:
        return [call["vars"] for call in self.calls if function in call["input"]]


class Killed(BaseException):
    """What a SIGKILL looks like from inside: nothing after it runs."""


class Children:
    """`subprocess.run`'s stand-in for the commands an operation runs."""

    def __init__(self, state_root: Path) -> None:
        self.calls: list[dict[str, Any]] = []
        self.state_root = state_root
        self.codes: dict[str, int] = {}
        self.password: str | None = None
        self.kill_at: str | None = None
        self.running = "true"
        #: What `admit.sh` prints instead of its decision, when a proof says so.
        self.admit_output: str | None = None
        #: The `database.public` the next deployed document records (outputs 22).
        self.doors: dict[str, Any] | None = None
        #: Where a `branch-runtime.sh` create or reset leaves its record (Session 40).
        self.branch_root: Path | None = None
        #: What `branch-runtime.sh start --all` prints (Session 41, D2514).
        self.branch_start_output = ""

    @staticmethod
    def label(argv: list[str]) -> str:
        name = Path(argv[0]).name
        if name == "deploy.sh":
            return "render-runtime" if "--render-runtime-only" in argv else "deploy"
        if name == "backup.sh":
            return "backup " + " ".join(argv[3:])
        if name == "project-runtime.sh":
            return "runtime " + argv[-1]
        if name == "branch-runtime.sh":
            return "branch " + argv[1]
        if name in ("systemctl", "docker"):
            return f"{name} {argv[1]}"
        return name

    def __call__(self, argv: list[str], **kwargs: Any) -> Any:
        label = self.label(argv)
        self.calls.append({"argv": list(argv), "label": label, **kwargs})
        if label == self.kill_at:
            raise Killed(label)
        out = ""
        if label == "auth-admin.sh":
            descriptor = int(argv[argv.index("--password-fd") + 1])
            with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as handle:
                self.password = handle.readline().removesuffix("\n")
            out = f"administrator created: {ADMIN_ID}\n"
        elif label == "deploy":
            manifest = yaml.safe_load(Path(argv[argv.index("--project") + 1]).read_text("utf-8"))
            self.deployed(manifest["compute"]["profile"])
            out = "deployed\n"
        elif label == "render-runtime":
            out = (
                f"  sudo bin/database-ports.sh verify --host host.yaml --instance-uuid {PRINTED}\n"
            )
        elif label == "docker inspect":
            out = self.running + "\n"
        elif label == "docker ps":
            out = STORAGE + "\n"
        elif label == "branch start":
            out = self.branch_start_output
        code = self.codes.get(label, 0)
        if label in ("branch create", "branch reset") and code == 0:
            self.branched(argv)
        if label == "admit.sh":
            safe = SAFE_REFUSED_MB if code == 12 else SAFE_ADMITTED_MB
            out = self.admit_output or json.dumps(
                {
                    "exit_code": code,
                    "reason": ADMISSION_REASON if code else None,
                    "lines": [
                        {"label": "requested", "value": f"{REQUESTED_MB} MiB for {KEY}"},
                        {"label": "safe available", "value": f"{safe} MiB"},
                    ],
                }
            )
        if kwargs.get("capture_output"):
            return subprocess.CompletedProcess(argv, code, out, "")
        handle = kwargs.get("stdout")
        if handle is not None and hasattr(handle, "write"):
            handle.write(out)
        return subprocess.CompletedProcess(argv, code, None, None)

    def deployed(self, profile: str) -> None:
        directory = self.state_root / KEY
        directory.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 21,
            "document_kind": "deployed",
            "project": {
                "key": KEY,
                "slug": "slot1",
                "environment": "dev",
                "domain": "slot1.example.test",
            },
            "template_version": "1.16.0",
            "source_commit": HEAD,
            "deployed_through_session": 38,
            "database": {"container": "apg-slot1-dev-postgres-1", "name": "slot1_dev"},
            "region": {"id": "eu-test-1"},
            "compute": {"profile": profile},
            "routes": {"app": {"url": "https://slot1.example.test/api/app", "status": "published"}},
        }
        if self.doors is not None:
            document["schema_version"] = 22
            document["database"]["public"] = self.doors
        (directory / "outputs.json").write_text(json.dumps(document), "utf-8")

    def branched(self, argv: list[str]) -> None:
        """What a finished runtime leaves: the branch's record, `ready`."""
        assert self.branch_root is not None
        name = argv[argv.index("--branch") + 1]
        point = argv[argv.index("--target-time") + 1] if "--target-time" in argv else None
        record = branch_record.Record(
            project_key=KEY, branch=name, state="ready", operation=OPERATION,
            requested_point=point, reached_point=point or BRANCH_REACHED, timeline=2,
            parent_commit=HEAD, pool_host=f"pool.{name}.slot1.example.test",
            direct_host=f"direct.{name}.slot1.example.test", expires_at=None,
            expires_for=None, unreclaimable_mb=640, created_at=BRANCH_REACHED,
            updated_at=BRANCH_REACHED,
        )  # fmt: skip
        branch_record.write(branch_record.record_path(KEY, name, root=self.branch_root), record)

    def labels(self) -> list[str]:
        return [call["label"] for call in self.calls]


class Host:
    """The roots a proof owns, the module pointed at them, and its recorders."""

    def __init__(self, module: Any, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.module = module
        self.root = root
        self.monkeypatch = monkeypatch
        self.database = Database([_row()])
        self.children = Children(module.STATE_ROOT)
        self.children.branch_root = module.BRANCH_ROOT
        self.checkout = (HEAD, "")
        monkeypatch.setattr(module.container_exec, "run", self.database)
        monkeypatch.setattr(module.subprocess, "run", self.children)
        monkeypatch.setattr(module, "checkout_reading", lambda owner, checkout=None: self.checkout)

    @property
    def slot_directory(self) -> Path:
        return self.module.SLOT_ROOT / KEY

    def prepare(self) -> None:
        """What `slot.sh prepare` and the provisioning sheet leave."""
        host = host_config.load_host_manifest(HOST)
        (entry,) = [e for e in host_config.declared_slots(host) if e.key == KEY]
        self.slot_directory.mkdir(mode=0o700, parents=True)
        manifest = self.slot_directory / slot.MANIFEST
        manifest.write_text(
            "# prepared\n" + yaml.safe_dump(slot.slot_manifest(host, entry), sort_keys=False),
            "utf-8",
        )
        manifest.chmod(0o600)
        state = self.module.STATE_ROOT / KEY
        state.mkdir(parents=True, exist_ok=True)
        (state / "bootstrap-state.json").write_text('{"runtime_identity_id": "id-1"}\n', "utf-8")
        generation = self.module.SECRET_ROOT / KEY / "generations" / "g1"
        generation.mkdir(parents=True)
        (generation / "manifest.json").write_text("{}", "utf-8")
        (self.module.SECRET_ROOT / KEY / "active-secret-generation.json").write_text(
            '{"generation_id": "g1"}\n', "utf-8"
        )

    def once(self) -> int:
        return self.module.main(["once"])

    def finished(self) -> dict[str, Any]:
        (finish,) = self.database.named("control_finish_operation")
        return {**finish, "result": json.loads(finish["result"])}


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    module = _load()
    for name in (
        "STATE_ROOT", "SLOT_ROOT", "SECRET_ROOT", "LOG_ROOT", "RUN_ROOT", "EXPORT_ROOT",
        "BRANCH_ROOT",
    ):  # fmt: skip
        monkeypatch.setattr(module, name, tmp_path / name.lower())
    monkeypatch.setattr(module, "SYSTEMD_DIR", tmp_path / "systemd")
    monkeypatch.setattr(module, "ENVIRONMENT_FILE", tmp_path / "etc" / "reconciler.env")
    monkeypatch.setattr(module, "HOST_MANIFEST", HOST)
    monkeypatch.setattr(module, "require_root", lambda: None)
    monkeypatch.setattr(module, "checkout_owner", lambda checkout=None: OWNER)
    monkeypatch.setattr(module, "dns_reading", lambda domain, expected: (True, "recorded"))
    monkeypatch.setattr(module, "control_target", lambda: module.Control(*CONTROL))
    monkeypatch.setattr(module.deployed_output, "read_deployed_document", lambda raw: raw)
    deployment = Host(module, tmp_path, monkeypatch)
    deployment.prepare()
    return deployment


# ---------------------------------------------------------------------------
# A creation, whole
# ---------------------------------------------------------------------------


def test_a_creation_runs_every_step_in_order(host: Host) -> None:
    """D2173: allocate, admit, deploy, the administrator, the ports, deploy,
    the unit, three backup commands, the registry -- each a recorded step --
    and the operation finishes succeeded with the declared members only."""
    assert host.once() == 0
    assert host.children.labels() == [
        "admit.sh",
        "deploy",
        "auth-admin.sh",
        "render-runtime",
        "database-ports.sh",
        "deploy",
        "systemctl enable",
        "backup backup --type full",
        "backup schedule enable",
        "backup mirror",
    ]
    finished = host.finished()
    assert finished["status"] == "succeeded" and finished["error_code"] == ""
    result = finished["result"]
    assert set(result) <= operations.RESULT_MEMBERS["project.create"]
    assert (result["project_key"], result["profile"], result["region"]) == (
        KEY,
        "standard",
        "eu-test-1",
    )
    steps = [name for name, _ in reconciler_dispatch.STEPS["project.create"]]
    assert [entry["step"] for entry in result["steps"]] == steps
    progress = [(v["step"], v["progress"]) for v in host.database.named("control_advance")]
    assert progress[0] == ("allocate", "10") and progress[-1] == ("registry", "90")
    assert {v["project_key"] for v in host.database.named("control_advance")} == {"", KEY}

    # The slot: taken by this operation, its manifest at the requested profile.
    marker = host.slot_directory / slot.ALLOCATED
    assert marker.read_text("utf-8").strip() == OPERATION
    assert oct(marker.stat().st_mode & 0o777) == "0o600"
    manifest = yaml.safe_load((host.slot_directory / slot.MANIFEST).read_text("utf-8"))
    assert manifest["compute"] == {"profile": "standard"}
    # The registry row: the display name, the slot, the region -- written once.
    (adopted,) = host.database.named("control_adopt_project")
    assert (adopted["key"], adopted["slot"], adopted["display_name"]) == (KEY, KEY, NAME)
    assert (adopted["organization"], adopted["region"], adopted["profile"]) == (
        ORG,
        "eu-test-1",
        "standard",
    )
    # The slot reading recorded at the start and after the operation.
    recorded = [json.loads(v["slots"]) for v in host.database.named("control_record_slots")]
    assert recorded[0] == [{"key": KEY, "state": "ready", "region_id": recorded[0][0]["region_id"]}]
    assert recorded[-1][0]["state"] == "allocated"


def test_every_argv_is_built_from_validated_members(host: Host) -> None:
    """D2154: of the arguments, only the administrator's username reaches an
    argv (the profile reaches the manifest the argv names); the display name and
    the handoff hash reach only a database, set on psql's stdin. And `verify`
    is BUILT from the volume's identity read from the database -- the line the
    runtime render printed is never executed (D2173)."""
    assert host.once() == 0
    every_argv = [call["argv"] for call in host.children.calls] + [
        call["argv"] for call in host.database.calls
    ]
    for argv in every_argv:
        assert isinstance(argv, list) and all(isinstance(part, str) for part in argv)
        for part in argv:
            assert NAME not in part and HANDOFF not in part, argv
            assert ORG not in part and REQUESTER not in part, argv

    username = ARGUMENTS["admin_username"]
    for call in host.children.calls:
        argv = call["argv"]
        assert Path(argv[0]).name in reconciler_dispatch.COMMANDS, argv
        for index, part in enumerate(argv):
            if part == username:
                assert argv[index - 1] in ("--username", "--display-name"), argv

    (verify,) = [c["argv"] for c in host.children.calls if c["label"] == "database-ports.sh"]
    assert verify[verify.index("--instance-uuid") + 1] == INSTANCE
    assert not any(PRINTED in part for argv in every_argv for part in argv)
    # The two values that reach only a database did reach it.
    (handoff,) = host.database.named("auth_open_password_reset")
    assert handoff == {"user": ADMIN_ID, "hash": HANDOFF}


def test_admission_refusal_is_capacity_exhausted_and_creates_nothing(host: Host) -> None:
    """D2160: admission runs after the slot is taken and BEFORE anything is
    rendered or deployed; exit 12 finishes the operation `capacity_exhausted
    {reason: admission}` with admission's sentence, and the slot is back to
    `ready` -- its prepared manifest restored byte for byte, its marker gone."""
    prepared = (host.slot_directory / slot.MANIFEST).read_bytes()
    host.children.codes["admit.sh"] = 12
    assert host.once() == 0
    assert host.children.labels() == ["admit.sh"]
    finished = host.finished()
    assert (finished["status"], finished["error_code"]) == ("failed", "capacity_exhausted")
    assert finished["result"]["reason"] == "admission"
    assert finished["result"]["refusal"] == ADMISSION_REASON
    assert finished["result"]["step"] == "admit"
    assert (host.slot_directory / slot.MANIFEST).read_bytes() == prepared
    assert not (host.slot_directory / slot.ALLOCATED).exists()
    assert not (host.module.STATE_ROOT / KEY / "outputs.json").exists()
    recorded = json.loads(host.database.named("control_record_slots")[-1]["slots"])
    assert recorded[0]["state"] == "ready"


def test_the_bootstrap_password_is_never_stored(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0260: the administrator's first password is random, handed to
    `auth-admin` through an inherited pipe, and written nowhere -- not an argv,
    not an environment, not a log, not a database call, not this command's output."""
    assert host.once() == 0
    password = host.children.password
    assert password and len(password) == 43, "the child read a password from the pipe"
    printed = capsys.readouterr()
    places = [printed.out, printed.err]
    places += [json.dumps(call["argv"]) for call in host.children.calls]
    places += [json.dumps(call.get("env") or {}) for call in host.children.calls]
    places += [call["input"] + json.dumps(call["argv"]) for call in host.database.calls]
    places += [p.read_text("utf-8") for p in host.module.LOG_ROOT.iterdir()]
    assert all(password not in place for place in places)
    (bootstrap,) = [c for c in host.children.calls if c["label"] == "auth-admin.sh"]
    descriptor = int(bootstrap["argv"][bootstrap["argv"].index("--password-fd") + 1])
    assert bootstrap["pass_fds"] == (descriptor,)


def test_children_act_for_the_checkout_owner_with_stdin_closed(host: Host) -> None:
    """D2153: every child carries SUDO_UID/SUDO_GID = the checkout's owner
    (the deploy hands `.generated/<key>` back by them, and git answers root
    on that checkout only with them -- rig 38g), runs in the checkout with
    stdin /dev/null, and writes its output to a 0600 log named for the
    operation and the step, in a 0700 directory."""
    assert host.once() == 0
    for call in host.children.calls:
        assert call["env"]["SUDO_UID"] == str(OWNER[0]), call["label"]
        assert call["env"]["SUDO_GID"] == str(OWNER[1]), call["label"]
        assert call["stdin"] is subprocess.DEVNULL, call["label"]
        assert call["cwd"] == REPO_ROOT, call["label"]
        assert call["timeout"] and call["timeout"] <= 1200, call["label"]
    logs = sorted(p.name for p in host.module.LOG_ROOT.iterdir())
    assert logs == sorted(
        f"{OPERATION}-{name}.log"
        for name, _ in reconciler_dispatch.STEPS["project.create"]
        if name not in ("allocate", "registry")
    )
    assert oct(host.module.LOG_ROOT.stat().st_mode & 0o777) == "0o700"
    assert {oct(p.stat().st_mode & 0o777) for p in host.module.LOG_ROOT.iterdir()} == {"0o600"}


def test_a_root_owned_checkout_is_refused(host: Host) -> None:
    """D2153: a root-owned checkout names nobody to act for."""
    real = _load()
    rooted = SimpleNamespace(stat=lambda: SimpleNamespace(st_uid=0, st_gid=0))
    with pytest.raises(real.OperatorError) as refused:
        real.checkout_owner(rooted)
    assert refused.value.code == 3
    # Control: the proof's own directory, owned by the user running it.
    owned = Path(host.root)
    assert real.checkout_owner(owned) == (owned.stat().st_uid, owned.stat().st_gid)


def test_a_moved_or_dirty_checkout_refuses_every_operation(host: Host) -> None:
    """D2179: HEAD read at start; an operation on a checkout whose HEAD moved,
    or whose tree is dirty, is finished `could_not_determine` with nothing run."""
    readings = iter([(HEAD, ""), ("b" * 40, "")])
    host.monkeypatch.setattr(
        host.module, "checkout_reading", lambda owner, checkout=None: next(readings)
    )
    assert host.once() == 0
    assert host.children.calls == []
    finished = host.finished()
    assert (finished["status"], finished["error_code"]) == ("failed", "could_not_determine")
    assert finished["result"] == {"reason": "checkout moved"}

    host.database.calls.clear()
    host.database.claims = [_row()]
    host.monkeypatch.setattr(
        host.module, "checkout_reading", lambda owner, checkout=None: (HEAD, " M deploy.sh")
    )
    assert host.once() == 0
    assert host.children.calls == []
    assert host.finished()["result"] == {"reason": "checkout moved"}


def test_invalid_arguments_run_nothing(host: Host) -> None:
    """D2154: validated against the schema file before anything runs; the
    reason names the type and never echoes the value that failed."""
    hostile = "ada; rm -rf /"
    host.database.claims = [_row(arguments={**ARGUMENTS, "admin_username": hostile})]
    assert host.once() == 0
    assert host.children.calls == []
    finished = host.finished()
    assert (finished["status"], finished["error_code"]) == ("failed", "invalid_request")
    assert hostile not in json.dumps(finished["result"])
    assert not (host.slot_directory / slot.ALLOCATED).exists()

    for arguments in ({**ARGUMENTS, "extra": "x"}, {**ARGUMENTS, "profile": "huge"}):
        host.database.calls.clear()
        host.database.claims = [_row(arguments=arguments)]
        assert host.once() == 0
        assert host.finished()["error_code"] == "invalid_request"
    assert host.children.calls == []


def test_no_ready_slot_is_capacity_exhausted_no_slot(host: Host) -> None:
    """D2160: a slot whose DNS record does not name this host is `prepared`,
    not `ready`; the creation is refused `no_slot` with nothing taken or run."""
    host.monkeypatch.setattr(host.module, "dns_reading", lambda d, e: (False, "no A record"))
    assert host.once() == 0
    assert host.children.calls == []
    finished = host.finished()
    assert finished["error_code"] == "capacity_exhausted"
    assert finished["result"]["reason"] == "no_slot"
    assert not (host.slot_directory / slot.ALLOCATED).exists()


def test_a_failed_deploy_fails_the_operation_and_keeps_the_slot(host: Host) -> None:
    """After the first deploy began, the slot is never returned: a failure is
    `operation_failed` naming the step, and the slot stays allocated for the
    operator (it is not reissued)."""
    host.children.codes["deploy"] = 5
    assert host.once() == 0
    assert host.children.labels() == ["admit.sh", "deploy"]
    finished = host.finished()
    assert (finished["error_code"], finished["result"]["step"]) == ("operation_failed", "deploy-1")
    assert (host.slot_directory / slot.ALLOCATED).read_text("utf-8").strip() == OPERATION


def test_the_closed_table_is_the_executed_types(host: Host) -> None:
    """ADR 0256: one handler per executed type and no other; one bound per
    command an operation may run."""
    assert set(host.module.HANDLERS) == set(reconciler_dispatch.STEPS)
    assert set(reconciler_dispatch.STEPS) == operations.EXECUTED_TYPES
    # Session 40 (D2434): four branch types, a restore being a creation at a point.
    branch_types = {"branch.create", "restore.create", "branch.reset", "branch.delete"}
    assert branch_types <= set(host.module.HANDLERS)
    assert host.module.HANDLERS["restore.create"] is host.module.HANDLERS["branch.create"]
    assert set(host.module.CHILD_SECONDS) == set(reconciler_dispatch.COMMANDS)


def test_an_interrupted_creation_is_finished_and_its_slot_quarantined(host: Host) -> None:
    """D2152, the command's half (the database's is test_reconciler_claim):
    a row left running is finished `failed interrupted` naming its step, its
    slot quarantined by the operation id the allocation marker carries, and
    nothing is run for it."""
    (host.slot_directory / slot.ALLOCATED).write_text(OPERATION + "\n", "utf-8")
    host.database.interrupted = [
        {"id": OPERATION, "type": "project.create", "step": "deploy-1", "project_key": KEY}
    ]
    host.database.claims = []
    assert host.once() == 0
    assert host.children.calls == []
    finished = host.finished()
    assert (finished["status"], finished["error_code"]) == ("failed", "interrupted")
    assert finished["result"] == {"step": "deploy-1"}
    assert (host.slot_directory / slot.QUARANTINED).read_text("utf-8").strip() == OPERATION


def test_two_control_projects_stop_the_reconciler(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2168: `control_registry.find_control`, the rule `control.sh` uses --
    two enabling documents is exit 5 at start, before any claim."""
    real = _load()
    monkeypatch.setattr(host.module, "control_target", real.control_target)
    monkeypatch.setattr(real, "STATE_ROOT", host.module.STATE_ROOT)

    def control_document(key: str) -> None:
        directory = host.module.STATE_ROOT / key
        directory.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 20,
            "project": {"key": key},
            "control": {"enabled": True},
            "database": {"container": f"apg-{key}-postgres-1", "name": key.replace("-", "_")},
        }
        (directory / "outputs.json").write_text(json.dumps(document), "utf-8")

    control_document("control-prod")
    assert host.once() == 0, "one control project: the reconciler starts"
    host.database.calls.clear()
    control_document("control-two")
    assert host.once() == 5
    assert host.database.calls == [], "nothing reached any database"


# ---------------------------------------------------------------------------
# The command's shape
# ---------------------------------------------------------------------------


def _calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def test_the_reconciler_builds_no_shell_command() -> None:
    """D2154's AST guard over the command and its table: no `shell=True`, no
    `os.system`/`os.popen`, no `subprocess` call whose command is a string."""
    sources = [REPO_ROOT / "bin" / "reconciler.py", Path(reconciler_dispatch.__file__)]
    runs = 0
    for path in sources:
        for call in _calls(path):
            for keyword in call.keywords:
                assert not (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value
                ), f"{path.name}:{call.lineno} shell=True"
            function = call.func
            if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                dotted = f"{function.value.id}.{function.attr}"
                assert dotted not in {"os.system", "os.popen", "subprocess.getoutput"}, (
                    f"{path.name}:{call.lineno} {dotted}"
                )
                if function.value.id == "subprocess" and call.args:
                    runs += 1
                    first = call.args[0]
                    assert not isinstance(first, (ast.Constant, ast.JoinedStr)), (
                        f"{path.name}:{call.lineno} a string command"
                    )
    # Control: the scan reaches the calls it is about.
    assert runs >= 4, runs


def test_the_unit_is_a_root_service_with_no_listener() -> None:
    """D2151: no socket, no port; stdin null (ADR 0218); restarted on failure
    every 30 s; the checkout named by the environment file `install` writes."""
    unit = configparser.ConfigParser(interpolation=None, strict=True)
    unit.optionxform = str  # type: ignore[assignment,method-assign]
    path = REPO_ROOT / "systemd" / "agentic-postgres-reconciler.service"
    unit.read_string(path.read_text("utf-8"))
    service = unit["Service"]
    assert service["Type"] == "simple"
    assert service["Restart"] == "on-failure" and service["RestartSec"] == "30"
    assert service["StandardInput"] == "null"
    assert service["EnvironmentFile"] == "/etc/agentic-postgres/reconciler.env"
    assert service["ExecStart"] == "/bin/bash ${APG_CHECKOUT}/bin/reconciler.sh run"
    assert "User" not in service, "root's: every command an operation runs is root's"
    assert set(unit.sections()) == {"Unit", "Service", "Install"}
    assert not any("listen" in option.lower() for s in unit.sections() for option in unit[s])
    assert "docker.service" in unit["Unit"]["After"]


def test_install_writes_the_unit_its_environment_and_its_directories(host: Host) -> None:
    """`reconciler.sh install`: the unit verbatim, the checkout named, the log
    and export directories 0700, then daemon-reload and enable --now."""
    module = host.module
    module.SYSTEMD_DIR.mkdir()
    assert module.main(["install"]) == 0
    unit = REPO_ROOT / "systemd" / module.UNIT
    assert (module.SYSTEMD_DIR / module.UNIT).read_bytes() == unit.read_bytes()
    assert module.ENVIRONMENT_FILE.read_text("utf-8") == f"APG_CHECKOUT={REPO_ROOT}\n"
    for directory in (module.LOG_ROOT, module.EXPORT_ROOT):
        assert oct(directory.stat().st_mode & 0o777) == "0o700"
    assert [call["argv"] for call in host.children.calls] == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", module.UNIT],
    ]


def test_status_reads_idle_working_and_stopped(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """D2178: what an operator's sheet reads before it deploys."""
    module = host.module
    answers = {"is-active": "active"}

    def systemctl(argv: list[str], **kwargs: Any) -> Any:
        word = answers.get(argv[1], "0")
        return subprocess.CompletedProcess(argv, 0, word + "\n", "")

    host.monkeypatch.setattr(module.subprocess, "run", systemctl)
    assert module.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "idle"
    module.RUN_ROOT.mkdir(parents=True)
    (module.RUN_ROOT / "reconciler.state.json").write_text(
        json.dumps({"operation": OPERATION, "type": "project.create", "step": "deploy-1"}), "utf-8"
    )
    assert module.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"working on {OPERATION} (project.create, step deploy-1)"
    )
    answers["is-active"] = "failed"
    assert module.main(["status"]) == 0
    assert capsys.readouterr().out.startswith("stopped (failed; last exit 0)")
    answers["is-active"] = "active"
    (module.RUN_ROOT / "reconciler.state.json").write_text("{", "utf-8")
    assert module.main(["status"]) == 6


def test_a_result_carries_only_declared_members() -> None:
    """D2151: the table's result members are the service's, and a member a
    type does not declare is refused before it reaches the database."""
    assert reconciler_dispatch.RESULT_MEMBERS is operations.RESULT_MEMBERS
    assert reconciler_dispatch.result("project.create", {"project_key": KEY}) == {
        "project_key": KEY
    }
    with pytest.raises(ValueError, match="download_url"):
        reconciler_dispatch.result("project.create", {"download_url": "https://x.invalid/"})


# ---------------------------------------------------------------------------
# Run 7: sleep, wake, resize, export, delete -- on a slot already created
# ---------------------------------------------------------------------------


def _deployed_slot(
    host: Host,
    operation_type: str,
    arguments: dict[str, Any] | None = None,
    *,
    doors: dict[str, Any] | None = None,
) -> None:
    """The slot created and running: allocated, its document deployed (with
    `doors` as its `database.public`, Session 39); one operation of
    `operation_type` pending on it."""
    (host.slot_directory / slot.ALLOCATED).write_text("an earlier creation\n", "utf-8")
    host.children.doors = doors
    host.children.deployed("small")
    host.database.claims = [_row(type=operation_type, arguments=arguments or {}, project_key=KEY)]


def test_sleep_disables_the_timers_and_the_unit_then_stops(host: Host) -> None:
    """D2155: the timers first (a timer firing would start a stopped project),
    the boot unit disabled (not stopped), then `project-runtime.sh stop` with
    the session the project was deployed through."""
    _deployed_slot(host, "project.sleep")
    assert host.once() == 0
    assert host.children.labels() == [
        "backup schedule disable",
        "systemctl disable",
        "runtime stop",
    ]
    stop = host.children.calls[-1]["argv"]
    assert stop[stop.index("--through-session") + 1] == "38"
    assert stop[stop.index("--project-key") + 1] == KEY
    assert host.children.calls[1]["argv"] == [
        "systemctl",
        "disable",
        f"agentic-postgres-project@{KEY}.service",
    ]
    finished = host.finished()
    assert (finished["status"], finished["secret"]) == ("succeeded", "")
    assert [s["step"] for s in finished["result"]["steps"]] == ["schedule", "unit", "stop"]


def test_wake_starts_the_same_containers_then_the_unit_and_the_timers(host: Host) -> None:
    """D2155: `start` (nothing materialized, rendered or built), then the unit
    enabled, then the timers."""
    _deployed_slot(host, "project.wake")
    assert host.once() == 0
    assert host.children.labels() == ["runtime start", "systemctl enable", "backup schedule enable"]
    assert host.finished()["status"] == "succeeded"


def test_resize_admits_a_candidate_before_anything_changes(host: Host) -> None:
    """D2160: admission reads a CANDIDATE manifest beside the slot's; refused
    (12), the operation is `capacity_exhausted {admission}` with the manifest
    byte for byte as it was, no candidate left and nothing deployed. Admitted,
    the manifest carries the new profile, one deploy, the registry refreshed
    without touching the display name."""
    _deployed_slot(host, "project.resize", {"profile": "large"})
    manifest = host.slot_directory / slot.MANIFEST
    before = manifest.read_bytes()
    host.children.codes["admit.sh"] = 12
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "admit.sh"]
    admitted = host.children.calls[1]["argv"]
    candidate = Path(admitted[admitted.index("--project") + 1])
    assert candidate.parent == host.slot_directory and candidate != manifest
    finished = host.finished()
    assert (finished["error_code"], finished["result"]["reason"]) == (
        "capacity_exhausted",
        "admission",
    )
    assert finished["result"]["refusal"] == ADMISSION_REASON
    assert manifest.read_bytes() == before
    assert sorted(p.name for p in host.slot_directory.iterdir()) == sorted(
        [slot.MANIFEST, slot.ALLOCATED]
    )

    # Control: admitted.
    host.database.calls.clear()
    host.children.calls.clear()
    host.children.codes.clear()
    host.database.claims = [
        _row(type="project.resize", arguments={"profile": "large"}, project_key=KEY)
    ]
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "admit.sh", "deploy"]
    assert yaml.safe_load(manifest.read_text("utf-8"))["compute"] == {"profile": "large"}
    assert host.finished()["result"]["profile"] == "large"
    (adopted,) = host.database.named("control_adopt_project")
    assert adopted["display_name"] == "" and adopted["profile"] == "large"


def test_the_export_names_only_the_customer_schemas(host: Host) -> None:
    """D2164 (rig 38d): `pg_dump -Fc -n app -n api -n public --no-owner
    --no-privileges` in the project's database container -- never
    `app_private`. `public` since Session 39 (D2333): the schema
    `customer_admin` creates the customer's own tables in -- exactly three."""
    _deployed_slot(host, "project.export")
    assert host.once() == 0
    (dump,) = [c for c in host.database.calls if c["argv"][:1] == ["pg_dump"]]
    assert dump["container"] == "apg-slot1-dev-postgres-1"
    assert dump["argv"] == [
        "pg_dump", "-U", "postgres", "-Fc", "-n", "app", "-n", "api", "-n", "public",
        "--no-owner", "--no-privileges", "-d", "slot1_dev",
    ]  # fmt: skip
    assert not any("app_private" in part for call in host.database.calls for part in call["argv"])


def test_the_export_url_is_the_operations_secret_and_the_archive_is_removed(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    """D2164: the archive written root 0600, streamed into the project's
    storage container (found by its labels), and REMOVED; the one URL the
    container printed is finished into the secret -- not the result, not a
    log, not this command's output. A failed upload removes the archive too."""
    _deployed_slot(host, "project.export")
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "docker ps"]
    (upload,) = [c for c in host.database.calls if "app.export_upload" in c["argv"]]
    assert upload["container"] == STORAGE
    assert upload["argv"][-1] == OPERATION and host.database.uploaded == ARCHIVE
    finished = host.finished()
    assert (finished["status"], finished["secret"]) == ("succeeded", URL)
    result = finished["result"]
    assert result["size_bytes"] == len(ARCHIVE)
    assert result["sha256"] == hashlib.sha256(ARCHIVE).hexdigest()
    assert "expires_at" in result and URL not in json.dumps(result)
    assert list(host.module.EXPORT_ROOT.iterdir()) == []
    printed = capsys.readouterr()
    assert URL not in printed.out + printed.err
    assert all(URL not in p.read_text("utf-8") for p in host.module.LOG_ROOT.iterdir())

    host.database.calls.clear()
    host.database.upload_code = 5
    host.database.claims = [_row(type="project.export", arguments={}, project_key=KEY)]
    assert host.once() == 0
    finished = host.finished()
    assert (finished["error_code"], finished["secret"]) == ("operation_failed", "")
    assert list(host.module.EXPORT_ROOT.iterdir()) == []


def test_a_sleeping_project_is_neither_exported_nor_resized(host: Host) -> None:
    """Its database is stopped: `invalid_request` (the state stays `sleeping`,
    D2203) with nothing dumped or admitted; no answer from docker is the third
    outcome."""
    for operation_type, arguments in (
        ("project.export", {}),
        ("project.resize", {"profile": "large"}),
    ):
        host.children.calls.clear()
        host.database.calls.clear()
        _deployed_slot(host, operation_type, arguments)
        host.children.running = "false"
        assert host.once() == 0
        assert host.children.labels() == ["docker inspect"], operation_type
        finished = host.finished()
        assert finished["error_code"] == "invalid_request"
        assert finished["result"]["reason"] == "the project is sleeping; wake it first"
    host.children.calls.clear()
    host.database.calls.clear()
    _deployed_slot(host, "project.export")
    host.children.running = ""
    assert host.once() == 0
    assert host.finished()["error_code"] == "could_not_determine"


def test_delete_consumes_the_slot(host: Host) -> None:
    """D2158: the retirement with the provider deferred and the data destroyed,
    its record in the slot's directory; then the tombstone (the operation's id),
    then the registry row marked deleted; the slot reads `consumed`."""
    _deployed_slot(host, "project.delete")
    assert host.once() == 0
    (retire,) = [c["argv"] for c in host.children.calls]
    assert retire[1:] == [
        "--host", str(REPO_ROOT / "host.yaml"),
        "--project", KEY,
        "--confirm", KEY,
        "--record", str(host.slot_directory / "retirement.json"),
        "--permanent", "--destroy-data", "--defer-provider",
    ]  # fmt: skip
    tombstone = host.slot_directory / slot.CONSUMED
    assert tombstone.read_text("utf-8").strip() == OPERATION
    assert oct(tombstone.stat().st_mode & 0o777) == "0o600"
    assert host.database.named("control_mark_deleted") == [{"key": KEY}]
    recorded = json.loads(host.database.named("control_record_slots")[-1]["slots"])
    assert recorded[0]["state"] == "consumed"
    assert host.finished()["status"] == "succeeded"


def test_an_operator_managed_project_is_refused(host: Host) -> None:
    """The reconciler stops, resizes, exports and retires only the slots it
    creates: a request naming alpha, beta or the control project -- each in
    the operator's organisation's registry -- runs nothing."""
    for key in ("alpha-dev", "control-prod"):
        host.database.calls.clear()
        host.database.claims = [_row(type="project.sleep", arguments={}, project_key=key)]
        assert host.once() == 0
        assert host.children.calls == []
        finished = host.finished()
        assert finished["error_code"] == "invalid_request"
        assert "operator-managed" in finished["result"]["reason"]


class _Clock:
    """A clock the proof advances only by sleeping, so 180 s takes no time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _Control:
    """The control database, answering after `failures` refusals."""

    def __init__(self, module: Any, failures: int) -> None:
        self.module = module
        self.failures = failures
        self.calls: list[str] = []

    def call(self, sql: str, **_: str) -> str:
        self.calls.append(sql)
        if len(self.calls) <= self.failures:
            raise self.module.ControlError("could not connect to server")
        return "1"


def test_start_waits_for_the_control_database(capsys: pytest.CaptureFixture[str]) -> None:
    """D2348: at a boot the control project's containers arrive after the edge,
    and `start` used to fail exit 6 on the first refusal (NRestarts 1 after
    Session 38's reboot). It now asks every 10 s and says so, and returns when
    the database answers -- here after 40 s. Control: a database that never
    answers fails exit 6 once 180 s are spent -- 18 waits, at 0 through 170 s,
    never a nineteenth."""
    module = _load()
    clock = _Clock()
    control = _Control(module, failures=4)
    module.wait_for_control(control, clock=clock, sleep=clock.sleep)
    assert len(control.calls) == 5 and clock.slept == [10] * 4
    printed = capsys.readouterr().out
    assert printed.count("waiting for the control project's database") == 4, printed
    assert "(30 s)" in printed

    clock = _Clock()
    never = _Control(module, failures=10**6)
    with pytest.raises(module.OperatorError) as raised:
        module.wait_for_control(never, clock=clock, sleep=clock.sleep)
    assert raised.value.code == module.EXIT_UNKNOWN
    assert "within 180 s" in str(raised.value)
    assert clock.now == module.CONTROL_WAIT_SECONDS and len(clock.slept) == 18, clock.slept

    # The wait is in `start`, between finding the control project and using it.
    source = (REPO_ROOT / "bin" / "reconciler.py").read_text(encoding="utf-8")
    body = source.split("def start() -> Reconciler:", 1)[1].split("\ndef ", 1)[0]
    assert body.index("control_target()") < body.index("wait_for_control(control)")
    assert body.index("wait_for_control(control)") < body.index("reconciler.recover()")


# ---------------------------------------------------------------------------
# Session 39: admission's reading in a resize's result (D2362, ADR 0270)
# ---------------------------------------------------------------------------


def test_a_resize_records_its_admission_reading_on_both_outcomes(host: Host) -> None:
    """D2362: the two numbers admission decided on travel in the operation's
    own result -- refused AND admitted -- so the lifecycle proof compares the
    outcome with its reading through `/v1` (ADR 0270). They are admission's
    lines, parsed; when admission printed none, no reading is invented."""
    _deployed_slot(host, "project.resize", {"profile": "large"})
    host.children.codes["admit.sh"] = 12
    assert host.once() == 0
    refused = host.finished()
    assert refused["error_code"] == "capacity_exhausted"
    assert refused["result"]["admission"] == {
        "requested_mb": REQUESTED_MB,
        "safe_available_mb": SAFE_REFUSED_MB,
    }
    assert REQUESTED_MB > SAFE_REFUSED_MB  # the reading implies the refusal

    host.database.calls.clear()
    host.children.calls.clear()
    host.children.codes.clear()
    host.database.claims = [_row(type="project.resize", arguments={"profile": "large"},
                                 project_key=KEY)]  # fmt: skip
    assert host.once() == 0
    admitted = host.finished()
    assert admitted["status"] == "succeeded"
    assert admitted["result"]["admission"] == {
        "requested_mb": REQUESTED_MB,
        "safe_available_mb": SAFE_ADMITTED_MB,
    }
    assert set(admitted["result"]) <= operations.RESULT_MEMBERS["project.resize"]

    # The third outcome: admission printed nothing readable -- no reading.
    host.database.calls.clear()
    host.children.calls.clear()
    host.children.admit_output = "not a decision"
    host.database.claims = [_row(type="project.resize", arguments={"profile": "large"},
                                 project_key=KEY)]  # fmt: skip
    assert host.once() == 0
    assert "admission" not in host.finished()["result"]


def test_admission_reading_reads_only_admissions_own_lines() -> None:
    reading = reconciler_dispatch.admission_reading
    lines = [
        {"label": "requested", "value": "840 MiB for slot1-dev"},
        {"label": "safe available", "value": "4600 MiB  (injected)"},
    ]
    assert reading(json.dumps({"lines": lines})) == {"requested_mb": 840, "safe_available_mb": 4600}
    assert reading(json.dumps({"lines": lines[:1]})) is None
    assert reading(json.dumps({"lines": [{"label": "requested", "value": "lots"}]})) is None
    assert reading("") is None
    assert reading("[]") is None


# ---------------------------------------------------------------------------
# Session 39: credential.rotate (ADR 0269, D2330)
# ---------------------------------------------------------------------------


def _rotation(host: Host, role: str = "customer_admin", **changes: Any) -> None:
    _deployed_slot(
        host,
        "credential.rotate",
        {"role": role, "verifier": VERIFIER, **changes},
        doors=DOORS,
    )


def test_a_rotation_sets_the_verifier_on_stdin_and_rewrites_both_userlists(host: Host) -> None:
    """D2330: the role's NAME read from the deployed document's door, never the
    argument; `ALTER ROLE` in the project's database with BOTH values psql
    variables on stdin; then `customer-credentials.sh sync` on the deployed
    document. The verifier is in no argv and in no result."""
    _rotation(host)
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "customer-credentials.sh"]
    (altered,) = [c for c in host.database.calls if "ALTER ROLE" in c["input"]]
    assert altered["container"] == "apg-slot1-dev-postgres-1"
    assert altered["vars"] == {"role": DIRECT_USER, "verifier": VERIFIER}
    assert reconciler_dispatch.ALTER_PASSWORD_SQL in altered["input"]
    sync = host.children.calls[-1]["argv"]
    assert Path(sync[0]).name == "customer-credentials.sh"
    assert sync[1:] == ["sync", "--outputs", str(host.module.STATE_ROOT / KEY / "outputs.json")]
    every_argv = [c["argv"] for c in host.children.calls] + [c["argv"] for c in host.database.calls]
    assert not any(VERIFIER in part for argv in every_argv for part in argv)
    finished = host.finished()
    assert finished["status"] == "succeeded"
    assert {k: v for k, v in finished["result"].items() if k != "steps"} == {
        "role": "customer_admin"
    }
    assert [s["step"] for s in finished["result"]["steps"]] == ["check", "alter", "sync"]
    assert VERIFIER not in json.dumps(finished["result"])

    # Control: the other role, the other door's user.
    host.database.calls.clear()
    host.children.calls.clear()
    _rotation(host, "customer_app")
    assert host.once() == 0
    (altered,) = [c for c in host.database.calls if "ALTER ROLE" in c["input"]]
    assert altered["vars"]["role"] == POOL_USER


def test_a_project_without_doors_is_refused_before_anything_runs(host: Host) -> None:
    for doors in (None, {"enabled": False, "pooled": None, "direct": None}):
        host.database.calls.clear()
        host.children.calls.clear()
        _deployed_slot(
            host, "credential.rotate", {"role": "customer_app", "verifier": VERIFIER}, doors=doors
        )
        assert host.once() == 0
        assert host.children.labels() == []
        assert not any("ALTER ROLE" in c["input"] for c in host.database.calls)
        finished = host.finished()
        assert (finished["error_code"], finished["result"]["reason"]) == (
            "invalid_request",
            "the project has no public endpoints",
        )


def test_a_refused_credential_fails_the_operation_and_syncs_nothing(host: Host) -> None:
    _rotation(host)
    host.database.refuse = "ALTER ROLE"
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect"]
    finished = host.finished()
    assert finished["error_code"] == "operation_failed"
    assert finished["result"]["reason"] == "the project's database refused the credential"
    assert "refused by the rig" not in json.dumps(finished["result"])


@pytest.mark.parametrize(
    "arguments",
    [
        {"role": "customer_app", "verifier": "hunter2"},
        {"role": "customer_app", "verifier": "md5" + "0" * 32},
        {"role": "customer_app", "verifier": VERIFIER + "\n"},
        {"role": "postgres", "verifier": VERIFIER},
        {"role": "customer_app", "verifier": VERIFIER, "password": "hunter2"},
    ],
)
def test_a_rotation_whose_arguments_are_not_a_verifier_runs_nothing(
    host: Host, arguments: dict[str, Any]
) -> None:
    _deployed_slot(host, "credential.rotate", arguments, doors=DOORS)
    assert host.once() == 0
    assert host.children.labels() == []
    assert not any("ALTER ROLE" in c["input"] for c in host.database.calls)
    assert host.finished()["error_code"] == "invalid_request"


def test_the_registry_refresh_records_the_doors(host: Host) -> None:
    """D2351: the refresh after a deploy carries the document's
    `database.public` whole; a document without it passes none (NULL), which
    the adoption reads as 'not named' and never erases."""
    _deployed_slot(host, "project.resize", {"profile": "large"}, doors=DOORS)
    assert host.once() == 0
    (adopted,) = host.database.named("control_adopt_project")
    assert json.loads(adopted["endpoints"]) == DOORS
    host.database.calls.clear()
    host.children.calls.clear()
    _deployed_slot(host, "project.resize", {"profile": "large"})
    assert host.once() == 0
    (adopted,) = host.database.named("control_adopt_project")
    assert adopted["endpoints"] == ""


# ---------------------------------------------------------------------------
# Session 40: branches and restore to a branch (ADR 0271, D2434, D2438, D2439)
# ---------------------------------------------------------------------------


def _branching(host: Host, operation_type: str, **changes: Any) -> None:
    _deployed_slot(host, operation_type, {**BRANCH_ARGUMENTS, **changes}, doors=DOORS)


def test_a_branch_create_is_argv_only(host: Host) -> None:
    """D2434: the parent read awake, then ONE `branch-runtime.sh create` on the
    parent's deployed document; the two verifiers are its stdin as JSON and in
    no argv; the expiry is set for the row's `requested_by`, never an argument
    (ADR 0272); then the branch reading recorded; the result is the record's."""
    _branching(host, "branch.create", expires_at=EXPIRES)
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "branch create"]
    call = host.children.calls[-1]
    argv = call["argv"]
    assert argv[argv.index("--parent-outputs") + 1] == str(
        host.module.STATE_ROOT / KEY / "outputs.json"
    )
    assert argv[argv.index("--branch") + 1] == "dev"
    assert argv[argv.index("--operation") + 1] == OPERATION
    assert argv[argv.index("--expires-at") + 1] == EXPIRES
    assert argv[argv.index("--expires-for") + 1] == REQUESTER
    assert "--verifiers-stdin" in argv and "--target-time" not in argv
    assert json.loads(call["input"]) == {"customer_app": VERIFIER, "customer_admin": VERIFIER}
    every_argv = [c["argv"] for c in host.children.calls] + [c["argv"] for c in host.database.calls]
    assert not any(VERIFIER in part for argv in every_argv for part in argv)
    assert host.database.named("control_record_branches"), "the branch reading was recorded"
    finished = host.finished()
    assert finished["status"] == "succeeded", finished
    assert {k: v for k, v in finished["result"].items() if k != "steps"} == {
        "branch": "dev",
        "reached_point": BRANCH_REACHED,
        "timeline": 2,
        "pool_host": "pool.dev.slot1.example.test",
        "direct_host": "direct.dev.slot1.example.test",
    }
    assert [s["step"] for s in finished["result"]["steps"]] == ["check", "runtime", "record"]
    assert VERIFIER not in json.dumps(finished["result"])


def test_a_restore_carries_its_point_and_a_reset_reuses_the_branch(host: Host) -> None:
    """`restore.create` is the creation's handler with `--target-time`, which
    its result names; `branch.reset` is `branch-runtime.sh reset`, verifiers
    on stdin as well."""
    _branching(host, "restore.create", target_time=POINT)
    assert host.once() == 0
    argv = host.children.calls[-1]["argv"]
    assert argv[1] == "create" and argv[argv.index("--target-time") + 1] == POINT
    restored = host.finished()["result"]
    assert (restored["target_time"], restored["reached_point"]) == (POINT, POINT)

    host.children.calls.clear()
    host.database.calls.clear()
    _branching(host, "branch.reset")
    assert host.once() == 0
    # The restore left a branch root, so this start brought its branch back first (D2439).
    assert host.children.labels() == ["branch start", "docker inspect", "branch reset"]
    reset = host.children.calls[-1]
    assert "--verifiers-stdin" in reset["argv"] and json.loads(reset["input"])
    assert host.finished()["status"] == "succeeded"


def test_a_branch_of_a_sleeping_parent_is_refused(host: Host) -> None:
    """A branch is restored through the parent's running database: asleep, a
    creation, a restore and a reset are `invalid_request` with nothing run but
    the reading. A deletion reads nothing of the parent (D2438) -- control:
    the same sleeping parent's branch is deleted."""
    for operation_type in ("branch.create", "restore.create", "branch.reset"):
        host.children.calls.clear()
        host.database.calls.clear()
        _branching(
            host, operation_type, **({"target_time": POINT} if "restore" in operation_type else {})
        )
        host.children.running = "false"
        assert host.once() == 0
        assert host.children.labels() == ["docker inspect"], operation_type
        finished = host.finished()
        assert finished["error_code"] == "invalid_request", operation_type
        assert finished["result"]["reason"] == "the project is sleeping; wake it first"

    host.children.calls.clear()
    host.database.calls.clear()
    _deployed_slot(host, "branch.delete", {"branch": "dev"}, doors=DOORS)
    host.children.running = "false"
    assert host.once() == 0
    assert host.children.labels() == ["branch delete"]
    assert host.children.calls[-1]["argv"][1:] == ["delete", "--parent-key", KEY, "--branch", "dev"]
    assert host.children.calls[-1].get("input") is None
    finished = host.finished()
    assert finished["status"] == "succeeded"
    assert {k: v for k, v in finished["result"].items() if k != "steps"} == {"branch": "dev"}


def test_a_point_outside_the_window_is_refused_before_the_restore(
    host: Host,
) -> None:
    """The window is decided by `branch-runtime.sh` before its restore phase
    (exit 7, `test_branch_runtime::test_a_point_outside_the_window_is_refused_
    before_anything_persists`); here, a restore to such a point is the
    customer's `invalid_request` with nothing recorded as a branch. Exit 12
    (admission) is `capacity_exhausted`; any other failure `operation_failed`.
    A parent without public endpoints is refused before anything runs."""
    host.children.codes = {"branch create": 7}
    _branching(host, "restore.create", target_time=POINT)
    assert host.once() == 0
    assert host.children.labels() == ["docker inspect", "branch create"]
    finished = host.finished()
    assert finished["error_code"] == "invalid_request"
    assert "restore window" in finished["result"]["reason"]
    assert not host.module.BRANCH_ROOT.exists(), "no record of a refused restore"
    for code, error in (
        (7, "invalid_request"),
        (12, "capacity_exhausted"),
        (1, "operation_failed"),
    ):
        host.children.calls.clear()
        host.database.calls.clear()
        host.children.codes = {"branch create": code}
        _branching(host, "branch.create")
        assert host.once() == 0
        assert host.finished()["error_code"] == error, code
    host.children.codes = {}
    host.children.calls.clear()
    host.database.calls.clear()
    _deployed_slot(host, "branch.create", dict(BRANCH_ARGUMENTS), doors=None)
    assert host.once() == 0
    assert host.children.labels() == []
    assert host.finished()["error_code"] == "invalid_request"


def test_start_brings_every_recorded_branch_back(host: Host) -> None:
    """D2439: a branch has no unit, so the reconciler's start runs
    `branch-runtime.sh start --all` and records the reading -- on a host that
    holds a branch root. Control: with no branch root nothing is started."""
    host.module.start()
    assert "branch start" not in host.children.labels()

    host.module.BRANCH_ROOT.mkdir(mode=0o700)
    host.database.calls.clear()
    host.module.start()
    (started,) = [c for c in host.children.calls if c["label"] == "branch start"]
    assert started["argv"][1:] == ["start", "--all"]
    assert started["stdin"] is subprocess.DEVNULL
    assert host.database.named("control_record_branches")


def test_the_branch_start_keeps_its_output(host: Host, capsys: pytest.CaptureFixture[str]) -> None:
    """D2514: `start --all`'s whole output goes to a 0600 log under the
    reconciler's log root and its LAST line reaches the journal -- before, the
    child's output was discarded and "a branch did not come back" carried no
    reason. Control: a start that came back says so, with its own last line."""
    host.module.BRANCH_ROOT.mkdir(mode=0o700)
    host.children.codes["branch start"] = 6
    host.children.branch_start_output = (
        "  slot3-prod_dev: did not come back: the parent's image changed since this branch "
        "was made (sha256:2794179a0000 -> sha256:7cbc07f10000); reset the branch\n"
    )
    capsys.readouterr()
    host.module.start()
    said = capsys.readouterr().out
    line = [entry for entry in said.splitlines() if "did not come back" in entry]
    assert len(line) == 1, said
    assert "(exit 6)" in line[0] and "the parent's image changed" in line[0], line
    logs = sorted(host.module.LOG_ROOT.glob("branch-start-*.log"))
    assert len(logs) == 1, logs
    assert oct(logs[0].stat().st_mode & 0o777) == "0o600"
    assert "reset the branch" in logs[0].read_text("utf-8")
    assert str(logs[0]) in line[0], "the journal line names the log it came from"

    host.children.codes["branch start"] = 0
    host.children.branch_start_output = (
        "  slot3-prod_dev: started from sha256:82700cbc1ab9, door ready\n"
    )
    host.module.start()
    back = [entry for entry in capsys.readouterr().out.splitlines() if "branches started" in entry]
    assert back and "door ready" in back[0], back
