"""The customer poolers' credentials: the userlists from `pg_authid`, and the two
doors running against a real cluster (Session 39, ADR 0269 items 3 and 5).

Three layers, each against the product's own code:

* `agentic_postgres.customer_credentials` -- the parse, the line, the rename,
  the modes;
* `bin/customer-credentials.py sync`, in process, with the cluster and Docker
  replaced: it never prints a verifier, it says "nothing to sync" for a project
  without the facility, and a pooler it could not signal is exit 6, never 0;
* (Docker) the locked cluster and the locked PgBouncer image, each pooler
  started from the ENTRYPOINT AND HEALTHCHECK `compose.yaml` declares, its
  userlist written by the verb's own `read_verifiers` and `write_userlist`:
  one role per door, an empty list refusing every login, a rotation reaching a
  running pooler by rename + SIGHUP, the daemon's own reading of its mode and
  claimant, and a healthcheck that is red when the userlist is absent.

**One deviation from the host, stated rather than hidden**: the rig is not
root, so it cannot write `root:70` 0640; it writes with no owner change and
then opens the modes to 0644/0755 for uid 70 to read. The modes the product
writes are asserted by the module tests, which is where they are decided.
"""

# ruff: noqa: S108 -- `/tmp` here is the POOLER CONTAINER's tmpfs and socket
# directory, never a path on this machine.

from __future__ import annotations

import functools
import importlib.util
import json
import os
import secrets
import stat
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.contract.test_image_contracts import requires_docker

from agentic_postgres import REPO_ROOT, customer_credentials, naming, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

MODEL = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
POOL, DIRECT = naming.CUSTOMER_POOL_SERVICE, naming.CUSTOMER_DIRECT_SERVICE
#: A real SCRAM-SHA-256 verifier's shape (PostgreSQL 18, 4096 iterations).
VERIFIER = (
    "SCRAM-SHA-256$4096:c2FsdHNhbHRzYWx0c2FsdA==$"
    "U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmU=:"
    "U2VydmVyS2V5U2VydmVyS2V5U2VydmVyS2V5U2VydmU="
)


def _verb() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_customer_credentials", REPO_ROOT / "bin" / "customer-credentials.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The module
# ---------------------------------------------------------------------------


def test_parse_reads_both_roles_and_a_null_as_no_credential() -> None:
    found = customer_credentials.parse_verifiers(
        f"customer_admin|\ncustomer_app|{VERIFIER}\n", ("customer_app", "customer_admin")
    )
    assert found == {"customer_app": VERIFIER, "customer_admin": None}


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        (f"customer_app|{VERIFIER}\n", "no role customer_admin"),
        ("customer_app|md5" + "0" * 32 + "\ncustomer_admin|\n", "not a SCRAM-SHA-256"),
        ("customer_app|plaintext\ncustomer_admin|\n", "not a SCRAM-SHA-256"),
        (f"postgres|{VERIFIER}\ncustomer_app|\ncustomer_admin|\n", "did not ask for"),
        ("garbage\n", "did not ask for"),
    ],
)
def test_parse_refuses_what_a_pooler_could_not_use(stdout: str, message: str) -> None:
    with pytest.raises(customer_credentials.CredentialError, match=message):
        customer_credentials.parse_verifiers(stdout, ("customer_app", "customer_admin"))


def test_a_userlist_names_one_role_or_nothing() -> None:
    assert customer_credentials.userlist("customer_app", VERIFIER) == (
        f'"customer_app" "{VERIFIER}"\n'
    )
    assert customer_credentials.userlist("customer_app", None) == ""
    with pytest.raises(customer_credentials.CredentialError):
        customer_credentials.userlist('app" "x', VERIFIER)


def test_a_write_is_a_rename_at_0640_and_leaves_no_staging_file(tmp_path: Path) -> None:
    customer_credentials.write_userlist(tmp_path, "pool.userlist", "one\n", gid=None)
    first = (tmp_path / "pool.userlist").stat()
    customer_credentials.write_userlist(tmp_path, "pool.userlist", "two\n", gid=None)
    second = (tmp_path / "pool.userlist").stat()
    assert (tmp_path / "pool.userlist").read_text() == "two\n"
    # A new inode: the pooler's DIRECTORY bind sees it, a file bind would not (rig 5a).
    assert first.st_ino != second.st_ino
    assert stat.S_IMODE(second.st_mode) == 0o640
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pool.userlist"]


def test_ensure_creates_empty_and_never_overwrites(tmp_path: Path) -> None:
    directory = tmp_path / "customer-poolers"
    customer_credentials.ensure_directory(directory, gid=None)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o750
    customer_credentials.ensure_userlist(directory, "pool.userlist", gid=None)
    assert (directory / "pool.userlist").read_text() == ""
    (directory / "pool.userlist").write_text("kept\n")
    customer_credentials.ensure_userlist(directory, "pool.userlist", gid=None)
    assert (directory / "pool.userlist").read_text() == "kept\n"


# ---------------------------------------------------------------------------
# The verb, in process
# ---------------------------------------------------------------------------


def _document(key: str, *, enabled: bool) -> dict[str, Any]:
    public: dict[str, Any] = {"enabled": False, "pooled": None, "direct": None}
    if enabled:
        public = {
            "enabled": True,
            "pooled": {"user": "customer_app"},
            "direct": {"user": "customer_admin"},
        }
    return {
        "project": {"key": key},
        "database": {"container": f"apg-{key}-postgres-1", "name": "app", "public": public},
    }


@pytest.fixture
def verb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    module = _verb()
    module.STATE_ROOT = tmp_path / "state"
    (tmp_path / "state" / "slot1-prod").mkdir(parents=True)
    monkeypatch.setattr(module, "require_root", lambda: None)
    real = module.customer_credentials
    monkeypatch.setattr(
        real, "ensure_directory", functools.partial(real.ensure_directory, gid=None)
    )
    monkeypatch.setattr(real, "write_userlist", functools.partial(real.write_userlist, gid=None))
    calls: dict[str, list] = {"psql": [], "signalled": []}

    def fake_run(container: str, *argv: str, **kwargs: Any) -> Any:
        calls["psql"].append((container, argv, kwargs))
        return subprocess.CompletedProcess(
            argv, 0, f"customer_admin|\ncustomer_app|{VERIFIER}\n", ""
        )

    monkeypatch.setattr(module.container_exec, "run", fake_run)
    module.calls = calls
    return module


def _sync(module: Any, tmp_path: Path, document: dict[str, Any]) -> int:
    outputs = tmp_path / "outputs.json"
    outputs.write_text(json.dumps(document), encoding="utf-8")
    return module.main(["sync", "--outputs", str(outputs)])


def test_sync_writes_one_role_per_door_and_never_prints_a_verifier(
    verb: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(verb, "signal", lambda container: verb.calls["signalled"].append(container))
    assert _sync(verb, tmp_path, _document("slot1-prod", enabled=True)) == 0
    directory = tmp_path / "state" / "slot1-prod" / "customer-poolers"
    assert (directory / "pool.userlist").read_text() == f'"customer_app" "{VERIFIER}"\n'
    assert (directory / "direct.userlist").read_text() == ""
    assert verb.calls["signalled"] == list(naming.customer_pooler_containers("slot1-prod"))
    # The names reached psql as variables, never in the query text.
    (container, argv, kwargs) = verb.calls["psql"][0]
    assert container == "apg-slot1-prod-postgres-1"
    assert "pool_role=customer_app" in argv and "direct_role=customer_admin" in argv
    assert kwargs["input"] == customer_credentials.VERIFIER_QUERY
    printed = capsys.readouterr()
    assert "SCRAM" not in printed.out + printed.err
    assert "pool.userlist: customer_app: credential set" in printed.out


def test_a_pooler_not_signalled_is_exit_6_never_success(
    verb: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(verb, "signal", lambda container: "No such container")
    assert _sync(verb, tmp_path, _document("slot1-prod", enabled=True)) == 6
    assert "were not told to re-read" in capsys.readouterr().err


def test_a_cluster_that_cannot_be_read_is_exit_6_and_writes_nothing(
    verb: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        verb.container_exec,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "container is not running"),
    )
    assert _sync(verb, tmp_path, _document("slot1-prod", enabled=True)) == 6
    assert not (tmp_path / "state" / "slot1-prod" / "customer-poolers").exists()


def test_without_the_facility_there_is_nothing_to_sync(
    verb: Any, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert _sync(verb, tmp_path, _document("alpha-dev", enabled=False)) == 0
    assert "has no public endpoints" in capsys.readouterr().out
    assert verb.calls["psql"] == []


def test_the_command_refuses_a_caller_who_is_not_root(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("this proof is about a caller who is not root")
    outputs = tmp_path / "outputs.json"
    outputs.write_text("{}", encoding="utf-8")
    done = subprocess.run(
        [str(REPO_ROOT / "bin" / "customer-credentials.sh"), "sync", "--outputs", str(outputs)],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    assert done.returncode == 3, done.stderr
    assert "must run as root" in done.stderr


# ---------------------------------------------------------------------------
# The poolers against a real cluster
# ---------------------------------------------------------------------------


def docker(*arguments: str, stdin: str | None = None, timeout: int = 120) -> Any:
    return subprocess.run(
        ["docker", *arguments], input=stdin, capture_output=True, text=True, check=False,
        timeout=timeout,
    )  # fmt: skip


def _lock() -> dict[str, str]:
    return {
        name: value
        for name, _, value in (
            line.partition("=")
            for line in (REPO_ROOT / "versions.env").read_text("utf-8").splitlines()
            if "=" in line and not line.startswith("#")
        )
    }


def _unescaped(text: str) -> str:
    """Compose's `$$` is a literal `$` in the container."""
    return text.replace("$$", "$")


class Rig:
    def __init__(self, token: str, lock: dict[str, str], directory: Path) -> None:
        self.network = f"apg-cp-{token}"
        self.cluster = f"apg-cp-{token}-pg"
        self.lock = lock
        self.directory = directory
        self.poolers = {POOL: f"apg-cp-{token}-pool", DIRECT: f"apg-cp-{token}-direct"}
        self.document = _document("cp", enabled=True)
        self.document["database"]["container"] = self.cluster
        self.verb = _verb()

    def sql(self, statement: str) -> None:
        done = docker(
            "exec", "-i", self.cluster, "psql", "-qtA", "-v", "ON_ERROR_STOP=1",
            "-U", "postgres", "-d", "app", stdin=statement,
        )  # fmt: skip
        assert done.returncode == 0, done.stderr

    def sync(self) -> None:
        """The verb's own read and write; the rig's only addition is the mode."""
        roles = self.verb.doors(self.document)
        verifiers = self.verb.read_verifiers(self.document, roles)
        for service, role in roles.items():
            filename = runtime_override.CUSTOMER_USERLISTS[service]
            text = customer_credentials.userlist(role, verifiers[role])
            customer_credentials.write_userlist(self.directory, filename, text, gid=None)
            (self.directory / filename).chmod(0o644)

    def start_pooler(self, service: str, name: str, *, bind: bool = True) -> None:
        model = MODEL["services"][service]
        environment = {
            "APG_CLUSTER_HOST": self.cluster,
            "APG_DATABASE_NAME": "app",
            "APG_POOL_MODE": model["environment"]["APG_POOL_MODE"],
            "APG_POOL_CONNECTIONS": "2",
            "APG_AUTH_FILE": model["environment"]["APG_AUTH_FILE"],
        }
        argv = ["run", "-d", "--name", name, "--network", self.network, "--user", "70:70",
                "--read-only", "--cap-drop", "ALL",
                "--tmpfs", "/etc/pgbouncer:rw,mode=0700,uid=70,gid=70",
                "--tmpfs", "/tmp:rw,mode=0700,uid=70,gid=70"]  # fmt: skip
        if bind:
            argv += ["-v", f"{self.directory}:{runtime_override.CUSTOMER_USERLIST_MOUNT}:ro"]
        for key, value in environment.items():
            argv += ["-e", f"{key}={value}"]
        argv += ["--entrypoint", "/bin/sh", self.lock["PGBOUNCER_IMAGE"], "-c",
                 _unescaped(model["entrypoint"][2])]  # fmt: skip
        done = docker(*argv)
        assert done.returncode == 0, done.stderr

    def healthy(self, service: str, name: str) -> bool:
        check = _unescaped(MODEL["services"][service]["healthcheck"]["test"][1])
        return docker("exec", name, "sh", "-c", check, timeout=30).returncode == 0

    def config(self, name: str) -> dict[str, str]:
        done = docker(
            "exec", name, "psql", "-h", "/tmp", "-p", "6432", "-U", "pgbouncer",
            "-d", "pgbouncer", "-w", "-X", "-qtA", "-c", "SHOW CONFIG",
        )  # fmt: skip
        assert done.returncode == 0, done.stderr
        return {
            fields[0]: fields[1]
            for fields in (line.split("|") for line in done.stdout.splitlines())
            if len(fields) > 1
        }

    def login(self, service: str, role: str, password: str) -> str | None:
        """`current_user` through one door, or None if the door refused."""
        done = docker(
            "run", "--rm", "--network", self.network, "-e", f"PGPASSWORD={password}",
            "--entrypoint", "psql", self.lock["POSTGRES_IMAGE"],
            f"host={self.poolers[service]} port=6432 dbname=app user={role} sslmode=disable",
            "-X", "-qtA", "-c", "SELECT current_user",
        )  # fmt: skip
        return done.stdout.strip() if done.returncode == 0 else None


def _wait(predicate: Any, seconds: int = 45) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    directory = tmp_path_factory.mktemp("customer-poolers")
    directory.chmod(0o755)
    created = Rig(secrets.token_hex(4), _lock(), directory)
    names = [created.cluster, *created.poolers.values(), f"{created.network}-nobind"]
    try:
        assert docker("network", "create", created.network).returncode == 0
        started = docker(
            "run", "-d", "--name", created.cluster, "--network", created.network,
            "-e", f"POSTGRES_PASSWORD={secrets.token_hex(24)}", "-e", "POSTGRES_DB=app",
            created.lock["POSTGRES_IMAGE"],
        )  # fmt: skip
        assert started.returncode == 0, started.stderr
        assert _wait(
            lambda: (
                docker(
                    "exec", created.cluster, "pg_isready", "-U", "postgres", "-d", "app"
                ).returncode
                == 0
                and docker(
                    "exec", created.cluster, "psql", "-U", "postgres", "-c", "SELECT 1"
                ).returncode
                == 0
            ),
            90,
        ), "the cluster never became ready"
        time.sleep(2)
        created.sql(
            "CREATE ROLE customer_app LOGIN; CREATE ROLE customer_admin LOGIN;\n"
            "SET password_encryption = 'scram-sha-256';\n"
            "ALTER ROLE customer_app PASSWORD 'first-app';\n"
        )
        created.sync()
        for service, name in created.poolers.items():
            created.start_pooler(service, name)
        for service, name in created.poolers.items():
            assert _wait(lambda s=service, n=name: created.healthy(s, n)), (
                f"{service} never healthy"
            )
        yield created
    finally:
        for name in names:
            docker("rm", "-fv", name)
        docker("network", "rm", created.network)


@requires_docker
def test_each_door_admits_its_one_role_and_an_empty_list_admits_nobody(rig: Rig) -> None:
    assert rig.login(POOL, "customer_app", "first-app") == "customer_app"
    # The pool's list names only customer_app (ADR 0269 item 3) ...
    assert rig.login(POOL, "customer_admin", "first-app") is None
    # ... and customer_admin has no credential yet: its list is empty.
    assert (rig.directory / "direct.userlist").read_text() == ""
    assert rig.login(DIRECT, "customer_admin", "anything") is None
    # The direct door does not admit the app role, which HAS a credential.
    assert rig.login(DIRECT, "customer_app", "first-app") is None


@requires_docker
def test_the_daemon_reads_its_mode_and_its_claimant(rig: Rig) -> None:
    for service, mode in ((POOL, "transaction"), (DIRECT, "session")):
        reading = rig.config(rig.poolers[service])
        assert reading["pool_mode"] == mode
        assert reading["max_db_connections"] == "2"
        assert reading["default_pool_size"] == "2"
        assert "search_path" in reading["track_extra_parameters"].lower()
        assert reading["auth_type"] == "scram-sha-256"
        assert reading["auth_file"] == MODEL["services"][service]["environment"]["APG_AUTH_FILE"]


@requires_docker
def test_a_rotation_reaches_the_running_poolers_by_rename_and_sighup(rig: Rig) -> None:
    rig.sql(
        "SET password_encryption = 'scram-sha-256';\n"
        "ALTER ROLE customer_app PASSWORD 'second-app';\n"
        "ALTER ROLE customer_admin PASSWORD 'first-admin';\n"
    )
    rig.sync()
    # The OLD credential still works before the pooler is told: a control that
    # the signal, not the write alone, is what moves the running daemon.
    assert rig.login(POOL, "customer_app", "first-app") == "customer_app"
    for name in rig.poolers.values():
        assert rig.verb.signal(name) is None
    assert _wait(lambda: rig.login(POOL, "customer_app", "second-app") == "customer_app", 15)
    assert rig.login(POOL, "customer_app", "first-app") is None
    assert rig.login(DIRECT, "customer_admin", "first-admin") == "customer_admin"
    assert rig.login(DIRECT, "customer_app", "second-app") is None


@requires_docker
def test_the_healthcheck_is_red_without_the_userlist(rig: Rig) -> None:
    name = f"{rig.network}-nobind"
    rig.start_pooler(POOL, name, bind=False)

    def answers() -> bool:
        try:
            return rig.config(name).get("pool_mode") == "transaction"
        except AssertionError:
            return False

    # The daemon answers its admin console (it logs the missing auth_file and
    # keeps listening) -- the control that the check could run at all ...
    assert _wait(answers, 30)
    # ... and the check still says no.
    assert not rig.healthy(POOL, name)
    assert rig.healthy(POOL, rig.poolers[POOL])
