"""`apg endpoint show|credential|connect` against the real control app (Session 39,
D2353, ADR 0269).

EP-CRED-001's client half. The control app is served by `control_cluster` and
**every command runs as a subprocess** -- `bin/login.sh`, `bin/endpoint.sh` --
exactly as a person types them (CLAUDE.md §7 question 6), each proof in a HOME
of its own. `psql` is a stand-in on the command's PATH that records what it was
handed: the argv, the passfile's path, mode and bytes, and whether `PGPASSWORD`
reached it.

The property: **the password never leaves this machine.** `credential`
generates it, writes it once 0600 BEFORE anything is sent, and sends only a
SCRAM verifier -- which the last proof sets on a real cluster and logs in with.
"""

# ruff: noqa: S608 -- every interpolated value is an id or a key this module
# minted, against a throwaway cluster.

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import control_cluster as cc
import pytest
from tests.contract.test_image_contracts import requires_docker

from agentic_postgres import REPO_ROOT, scram
from app import operations

pytestmark = [pytest.mark.contract, pytest.mark.database, pytest.mark.security, pytest.mark.p0]

BIN = REPO_ROOT / "bin"

#: The stand-in psql: records what it was handed, then exits 3 -- so a proof can
#: tell psql's own status from the command's.
FAKE_PSQL = """#!/usr/bin/env python3
import json, os, stat, sys
passfile = os.environ.get("PGPASSFILE", "")
info = os.stat(passfile) if passfile and os.path.exists(passfile) else None
record = {
    "argv": sys.argv[1:],
    "passfile": passfile,
    "mode": stat.S_IMODE(info.st_mode) if info else None,
    "dir_mode": stat.S_IMODE(os.stat(os.path.dirname(passfile)).st_mode) if info else None,
    "content": open(passfile).read() if info else None,
    "pgpassword": "PGPASSWORD" in os.environ,
}
with open(os.environ["FAKE_PSQL_RECORD"], "w") as handle:
    json.dump(record, handle)
sys.exit(3)
"""


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.served_app(cluster, tmp_path_factory.mktemp("endpoint-cli")) as pair:
                yield pair
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def accepting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every executed type accepted, for this proof only: the served app runs in
    this process, so the module the routes read is the one patched."""
    monkeypatch.setattr(operations, "ACCEPTED_TYPES", operations.EXECUTED_TYPES)


class Person:
    """One person at one terminal: a HOME of their own, a stand-in psql."""

    def __init__(self, home: Path, endpoint: str) -> None:
        self.home = home
        self.endpoint = endpoint
        self.tools = home / "tools"
        self.tools.mkdir()
        psql = self.tools / "psql"
        psql.write_text(FAKE_PSQL, encoding="utf-8")
        psql.chmod(0o755)
        self.record = home / "psql-record.json"

    def run(self, command: str, *argv: str, extra_env: dict[str, str] | None = None) -> Any:
        environment = {
            "PATH": f"{self.tools}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "FAKE_PSQL_RECORD": str(self.record),
            **(extra_env or {}),
        }
        return subprocess.run(
            [str(BIN / f"{command}.sh"), *argv],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environment,
            timeout=120, check=False,
        )  # fmt: skip

    def login(self, username: str) -> None:
        password = self.home / f"{username}.password"
        password.write_text(cc.PASSWORD + "\n", encoding="utf-8")
        password.chmod(0o600)
        done = self.run("login", "password", "--endpoint", self.endpoint, "--username",
                        username, "--password-file", str(password))  # fmt: skip
        assert done.returncode == 0, done.stderr


@pytest.fixture
def person(served: Any, tmp_path: Path) -> Person:
    endpoint, _ = served
    home = tmp_path / "home"
    home.mkdir()
    return Person(home, endpoint)


def _project(served: Any, label: str, role: str = "member") -> tuple[str, str, str]:
    """(username, organisation, project key): a `role` of a fresh organisation
    whose project was adopted with doors."""
    _, drive = served
    tag = f"{label}-{uuid.uuid4().hex[:6]}"
    owner = drive.account(f"{tag}-owner")
    org = drive.organization(owner, tag)
    user = drive.account(tag)
    drive.member(org, user, role)
    key = f"e{uuid.uuid4().hex[:8]}-prod"
    stem = key.replace("-", "_")
    doors = {
        "enabled": True,
        "pooled": {"host": f"pool.{key}.example.com", "port": 5432,
                   "user": f"{stem}_customer_app", "database": stem,
                   "sslmode": "verify-full", "connection_limit": 2},
        "direct": {"host": f"direct.{key}.example.com", "port": 5432,
                   "user": f"{stem}_customer_admin", "database": stem,
                   "sslmode": "verify-full", "connection_limit": 2},
    }  # fmt: skip
    drive.cluster.query(
        f"SELECT app.control_adopt_project('{key}', '{org}', '{key[:9]}', 'prod', "
        f"'{key}.test', '1.17.0', 'abc', p_endpoints => '{json.dumps(doors)}'::jsonb)"
    )
    return tag, org, key


def _rows(drive: Any, key: str) -> list[str]:
    return drive.cluster.query(
        f"SELECT arguments::text FROM app.control_operations WHERE project_key = '{key}' "
        "ORDER BY created_at"
    )


def _verifies(verifier: str, password: str) -> bool:
    """Does `verifier` admit `password`? Recomputed with the verifier's own salt."""
    salt = base64.b64decode(verifier.split("$")[1].split(":")[1])
    return scram.verifier(password, salt=salt) == verifier


# ---------------------------------------------------------------------------
# credential
# ---------------------------------------------------------------------------


def test_the_password_never_leaves_the_workstation(
    person: Person, served: Any, accepting: None
) -> None:
    """The row the server recorded carries the role and a verifier OF the
    password in the file -- and nothing of the password; no output prints it."""
    _, drive = served
    user, _org, key = _project(served, "cred")
    person.login(user)
    output = person.home / "app.password"
    done = person.run("endpoint", "credential", "--project-key", key, "--role", "app",
                      "--password-file", str(output), "--json")  # fmt: skip
    assert done.returncode == 0, done.stderr
    password = output.read_text(encoding="utf-8").strip()
    assert len(password) == 43
    (arguments,) = _rows(drive, key)
    recorded = json.loads(arguments)
    assert set(recorded) == {"role", "verifier"} and recorded["role"] == "customer_app"
    assert scram.VERIFIER.fullmatch(recorded["verifier"])
    assert _verifies(recorded["verifier"], password)
    assert not _verifies(recorded["verifier"], password + "x")  # the control
    assert password not in arguments
    assert password not in done.stdout + done.stderr
    assert json.loads(done.stdout)["operation"]["type"] == "credential.rotate"


def test_the_password_file_is_private_and_written_once(
    person: Person, served: Any, accepting: None
) -> None:
    """0600, created exclusively: an existing file is refused (exit 2) before a
    password is made or a request sent; a request the server refuses leaves no
    file behind, because no credential was recorded."""
    _, drive = served
    user, _org, key = _project(served, "once")
    person.login(user)
    output = person.home / "admin.password"
    first = person.run("endpoint", "credential", "--project-key", key, "--role", "admin",
                       "--password-file", str(output))  # fmt: skip
    assert first.returncode == 0, first.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    kept = output.read_bytes()
    again = person.run("endpoint", "credential", "--project-key", key, "--role", "admin",
                       "--password-file", str(output))  # fmt: skip
    assert again.returncode == 2 and "already exists" in again.stderr, again.stderr
    assert output.read_bytes() == kept
    assert len(_rows(drive, key)) == 1

    # Refused by the server (one rotation is already in flight on the project):
    # the new file is removed.
    second = person.home / "second.password"
    refused = person.run("endpoint", "credential", "--project-key", key, "--role", "app",
                         "--password-file", str(second))  # fmt: skip
    assert refused.returncode == 5 and "conflict" in refused.stderr, refused.stderr
    assert not second.exists()


def test_credential_wait_reads_the_outcome(person: Person, served: Any, accepting: None) -> None:
    """`--wait` follows the operation: finished `succeeded` by the reconciler's
    half (the superuser, as the reconciler writes it), the command says the
    previous password no longer works; `failed`, exit 5."""
    _, drive = served
    user, _org, key = _project(served, "wait")
    person.login(user)
    outcomes: dict[str, Any] = {}

    def finish(status: str, code: str | None) -> None:
        """THIS project's pending row -- never the oldest pending row, which an
        earlier proof in the module may have left -- running, then finished."""
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            pending = drive.cluster.query(
                "SELECT id FROM app.control_operations "
                f"WHERE project_key = '{key}' AND status = 'pending'"
            )
            if pending:
                drive.cluster.query(
                    "UPDATE app.control_operations SET status = 'running', started_at = now(), "
                    f"attempt = attempt + 1 WHERE id = '{pending[0]}'"
                )
                literal = "NULL" if code is None else f"'{code}'"
                drive.cluster.query(
                    f"SELECT app.control_finish_operation('{pending[0]}', '{status}', "
                    f'{literal}, \'{{"role": "customer_app"}}\'::jsonb)'
                )
                return
            time.sleep(0.2)

    for status, code, expected in (
        ("succeeded", None, 0),
        ("failed", "operation_failed", 5),
    ):
        output = person.home / f"{status}.password"
        worker = threading.Thread(target=finish, args=(status, code))
        worker.start()
        done = person.run("endpoint", "credential", "--project-key", key, "--role", "app",
                          "--password-file", str(output), "--wait", "--interval", "1",
                          "--timeout", "60")  # fmt: skip
        worker.join()
        outcomes[status] = done
        assert done.returncode == expected, (status, done.stderr)
    assert "no longer works" in outcomes["succeeded"].stdout


# ---------------------------------------------------------------------------
# show and connect
# ---------------------------------------------------------------------------


def test_show_names_both_doors_and_no_password(person: Person, served: Any) -> None:
    user, _org, key = _project(served, "show", role="viewer")
    person.login(user)
    done = person.run("endpoint", "show", "--project-key", key, "--json")
    assert done.returncode == 0, done.stderr
    served_doors = json.loads(done.stdout)
    assert served_doors["pooled"]["host"] == f"pool.{key}.example.com"
    text = person.run("endpoint", "show", "--project-key", key)
    assert f"pool.{key}.example.com:5432" in text.stdout
    assert f"direct.{key}.example.com:5432" in text.stdout
    assert "<password from your file>" in text.stdout


def test_connect_hands_psql_a_private_passfile_and_removes_it(person: Person, served: Any) -> None:
    """psql gets the door's conninfo -- `verify-full` against the system's
    authorities -- and the arguments after `--`; the password only through a
    0600 PGPASSFILE in a 0700 directory, never `PGPASSWORD` (set in the caller's
    environment and NOT passed on); both gone when psql ends; psql's own exit
    status is the command's."""
    user, _org, key = _project(served, "connect", role="viewer")
    person.login(user)
    password_file = person.home / "admin.password"
    password = secrets.token_urlsafe(32)
    password_file.write_text(password + "\n", encoding="utf-8")
    password_file.chmod(0o600)
    done = person.run(
        "endpoint", "connect", "--project-key", key, "--role", "admin",
        "--password-file", str(password_file), "--", "-c", "select 1",
        extra_env={"PGPASSWORD": "leaked-from-the-environment"},
    )  # fmt: skip
    assert done.returncode == 3, done.stderr
    record = json.loads(person.record.read_text(encoding="utf-8"))
    stem = key.replace("-", "_")
    assert record["argv"] == [
        f"host=direct.{key}.example.com port=5432 dbname={stem} user={stem}_customer_admin "
        "sslmode=verify-full sslrootcert=system",
        "-c",
        "select 1",
    ]
    assert record["mode"] == 0o600 and record["dir_mode"] == 0o700
    assert record["content"] == (
        f"direct.{key}.example.com:5432:{stem}:{stem}_customer_admin:{password}\n"
    )
    assert record["pgpassword"] is False
    assert not Path(record["passfile"]).exists()
    assert not Path(record["passfile"]).parent.exists()
    assert all(password not in part for part in record["argv"])
    assert password not in done.stdout + done.stderr

    # A file that is not private is refused before psql runs.
    password_file.chmod(0o644)
    person.record.unlink()
    wide = person.run("endpoint", "connect", "--project-key", key, "--role", "app",
                      "--password-file", str(password_file))  # fmt: skip
    assert wide.returncode == 3, wide.stderr
    assert not person.record.exists()


# ---------------------------------------------------------------------------
# The verifier on a real cluster
# ---------------------------------------------------------------------------


@requires_docker
def test_a_verifier_from_here_admits_its_password_on_postgresql() -> None:
    """`scram.verifier` is what PostgreSQL stores: set as a role's password
    VERBATIM (PostgreSQL keeps a SCRAM-shaped value as it is), the password
    logs in with SCRAM and another password does not.

    From ANOTHER container over a network: the image trusts loopback
    (`host all all 127.0.0.1/32 trust`), so a login inside the cluster's own
    container admits any password -- which is how this proof's first version
    passed its positive half and failed its control."""
    lock = {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }
    name = f"apg-scram-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(32)
    verifier = scram.verifier(password)

    def docker(*argv: str, stdin: str | None = None) -> Any:
        return subprocess.run(["docker", *argv], input=stdin, capture_output=True, text=True,
                              timeout=120, check=False)  # fmt: skip

    assert docker("network", "create", name).returncode == 0
    started = docker("run", "-d", "--name", name, "--network", name, "-e",
                     f"POSTGRES_PASSWORD={secrets.token_hex(16)}",
                     lock["POSTGRES_IMAGE"])  # fmt: skip
    assert started.returncode == 0, started.stderr
    try:
        # Two answers in a row: the image's init answers once, then restarts.
        deadline, rounds = time.monotonic() + 90, 0
        while time.monotonic() < deadline and rounds < 2:
            answered = docker("exec", name, "psql", "-U", "postgres", "-c", "SELECT 1")
            rounds = rounds + 1 if answered.returncode == 0 else 0
            time.sleep(1)
        assert rounds >= 2, "the cluster never became ready"
        set_it = docker("exec", "-i", name, "psql", "-U", "postgres", "-v", "ON_ERROR_STOP=1",
                        "-v", f"verifier={verifier}",
                        stdin="CREATE ROLE probe LOGIN PASSWORD :'verifier';\n"
                              "SELECT rolpassword = :'verifier' FROM pg_authid "
                              "WHERE rolname = 'probe';\n")  # fmt: skip
        assert set_it.returncode == 0 and "t" in set_it.stdout.split(), set_it.stderr

        def login(secret: str) -> Any:
            return docker("run", "--rm", "--network", name, "-e", f"PGPASSWORD={secret}",
                          "--entrypoint", "psql", lock["POSTGRES_IMAGE"],
                          f"host={name} user=probe dbname=postgres sslmode=disable",
                          "-tAc", "SELECT current_user")  # fmt: skip

        admitted = login(password)
        assert admitted.returncode == 0 and admitted.stdout.strip() == "probe", admitted.stderr
        refused = login(password + "x")
        assert refused.returncode != 0 and "password authentication failed" in refused.stderr
    finally:
        docker("rm", "-fv", name)
        docker("network", "rm", name)
