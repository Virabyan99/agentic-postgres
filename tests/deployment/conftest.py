"""Shared plumbing for the host-local suite.

Everything here runs only on a provisioned deployment host, admitted by the
``requires_environment`` gate in ``tests/conftest.py``. Reading an environment
variable directly with ``os.environ[...]`` is deliberate: the gate has already
established the variable is set, so a ``KeyError`` here means the harness is
wrong, and that must surface as an error rather than as a skip.

Helpers are exposed as fixtures rather than as importable functions. ``tests/``
is not a package, so a test module cannot import its own conftest by name
without adding ``__init__.py`` files whose only purpose would be to make an
import work.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres.naming import HEALTH_ROUTE_PATH

#: Signature of the plain-output command runner returned by the ``sh`` fixture.
Runner = Callable[..., str]

#: Signature of the exit-code-preserving runner returned by ``sh_status``.
StatusRunner = Callable[..., tuple[int, str, str]]


def _resolve(command: tuple[str, ...]) -> list[str]:
    first = command[0]
    executable = first if first.startswith("/") else shutil.which(first)
    if executable is None:
        pytest.fail(f"{first} is not installed on this host")
    return [executable, *command[1:]]


@pytest.fixture(scope="session")
def sh() -> Runner:
    """Run a host command and return stdout, failing the test on a bad exit.

    Failure is a test failure carrying stderr rather than a raised exception:
    on a live host the useful information is what the tool said, not where
    Python was standing when it said it.
    """

    def run(*command: str) -> str:
        result = subprocess.run(_resolve(command), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            pytest.fail(
                f"`{' '.join(command)}` exited {result.returncode}\n"
                f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
            )
        return result.stdout

    return run


@pytest.fixture(scope="session")
def sh_status() -> StatusRunner:
    """Run a command and return ``(exit code, stdout, stderr)`` unjudged."""

    def run(*command: str) -> tuple[int, str, str]:
        result = subprocess.run(_resolve(command), capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr

    return run


@pytest.fixture(scope="session")
def as_root() -> None:
    """Fail rather than skip when root-only state is unreadable.

    A skip here would report "environment absent" for a run that *is* on the
    host and simply forgot ``sudo``, which is the one case where a quiet skip
    would hide a real gap in the evidence.
    """
    if os.geteuid() != 0:
        pytest.fail(
            "this test reads root-only host state; run it through "
            "`sudo bin/session-02-check.sh --mode host`"
        )


@pytest.fixture(scope="session")
def probe_image() -> str:
    """The digest-pinned image used for in-network probes.

    A floating tag here would make the probe's behaviour depend on whatever was
    published today, in a test whose whole purpose is to characterise a
    security boundary.
    """
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "PYTHON_RUNTIME_IMAGE":
            return value.strip()
    pytest.fail("PYTHON_RUNTIME_IMAGE is absent from versions.env")


def load_deployed(variable: str) -> dict[str, Any]:
    path = Path(os.environ[variable])
    if not path.is_file():
        pytest.fail(f"{variable} points at {path}, which does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def project_a() -> dict[str, Any]:
    return load_deployed("APG_PROJECT_A_OUTPUTS")


@pytest.fixture(scope="session")
def project_b() -> dict[str, Any]:
    return load_deployed("APG_PROJECT_B_OUTPUTS")


@pytest.fixture(scope="session")
def running_containers(sh: Runner) -> list[dict[str, Any]]:
    """Every running container, as parsed JSON rather than scraped columns."""
    raw = sh("docker", "ps", "--format", "{{json .}}")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


#: Where the materializer writes a project's secret generations (ADR 0020).
SECRET_ROOT = Path("/var/lib/agentic-postgres/secrets")


@pytest.fixture(scope="session")
def migration_password() -> Callable[[str], str]:
    """One project's live migration credential, from the generation it points at.

    Root-only, and read the same way ``bin/postgres-bootstrap.py`` reads it --
    through ``active-secret-generation.json`` rather than by listing
    ``generations/`` and taking the newest. The generations accumulate; the
    pointer is the only statement about which one the project is using, and a
    directory listing sorted by name is a fact about mtime standing in for that.

    ``.rstrip("\\n")`` and nothing more, because the dbmate entrypoint reads the
    same file with ``$(cat ...)``, which strips exactly trailing newlines. A
    ``.strip()`` here would produce a value the container does not present and a
    login failure nobody could explain.
    """

    def read(project_key: str) -> str:
        pointer = SECRET_ROOT / project_key / "active-secret-generation.json"
        if not pointer.is_file():
            pytest.fail(f"{project_key} has no active secret generation at {pointer}")
        generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
        path = SECRET_ROOT / project_key / "generations" / generation / "dbmate"
        path = path / "migration_user_password"
        if not path.is_file():
            pytest.fail(f"generation {generation} of {project_key} has no migration credential")
        value = path.read_text(encoding="utf-8").rstrip("\n")
        assert value, f"the migration credential for {project_key} is empty"
        return value

    return read


#: Where the deploy installs each project's rendered output (ADR 0020).
RENDERED_ROOT = Path("/var/lib/agentic-postgres/rendered")

#: How long a route may take to reappear after its project restarts.
#:
#: Bounded, and short enough that a project which never comes back is a failure
#: rather than a long wait. Measured cause: `systemctl start` returns when the
#: containers are healthy and the edge is attached, but Traefik *discovers* its
#: backends rather than being told about them, so the router for a recreated
#: edge network appears a moment later. Session 2 never lost this race because a
#: Session 2 project's stack came back in about a second; a Session 3 project
#: takes long enough that the window is reachable (D75).
ROUTE_RETURN_TIMEOUT_SECONDS = 90


@pytest.fixture(scope="session")
def await_health() -> Callable[[str, str], dict[str, Any]]:
    """Poll a project's health route until it identifies that project.

    Only for the moment *after* a restart. A steady-state assertion must stay
    immediate: a route that is down while nothing is happening to it is a
    failure, and wrapping that in a retry would turn a broken deployment into a
    slow green.
    """

    def poll(hostname: str, project_key: str) -> dict[str, Any]:
        context = ssl.create_default_context()
        deadline = time.monotonic() + ROUTE_RETURN_TIMEOUT_SECONDS
        last = "no attempt was made"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(
                    f"https://{hostname}{HEALTH_ROUTE_PATH}", timeout=15, context=context
                ) as response:
                    payload = json.loads(response.read())
                if payload.get("project_key") == project_key:
                    return payload
                last = f"answered for {payload.get('project_key')!r}"
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
        pytest.fail(
            f"https://{hostname}{HEALTH_ROUTE_PATH} did not identify {project_key} "
            f"within {ROUTE_RETURN_TIMEOUT_SECONDS}s; last: {last}"
        )

    return poll


@pytest.fixture(scope="session")
def rendered_document() -> Callable[[str], dict[str, Any]]:
    """One project's rendered document, as installed on the host.

    The deployed document does not carry ``compose``: the two branches of
    ``outputs.schema.json`` are deliberately different documents, and the volume
    name, the network names and the Compose project name live only on the
    rendered branch. Two Session 3 tests read ``document["compose"]`` out of a
    deployed document and had never run, because both need two deployed projects
    and there was only ever one (D73).

    Read from ``/var/lib/agentic-postgres/rendered/<key>/`` rather than from the
    checkout's ``.generated/``: the installed copy is the one the running
    containers were started from, and the checkout's is whatever the operator
    last rendered.
    """

    def read(project_key: str) -> dict[str, Any]:
        path = RENDERED_ROOT / project_key / "outputs.json"
        if not path.is_file():
            pytest.fail(f"{project_key} has no installed rendered document at {path}")
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["document_kind"] == "rendered", (
            f"{path} is a {document['document_kind']} document"
        )
        return document

    return read


@pytest.fixture(scope="session")
def pg_login() -> Callable[[dict[str, Any], str, str, str], tuple[int, str, str]]:
    """Attempt a password login against a project's cluster. Returns, never judges.

    **From a container on the project's internal network, not from inside the
    cluster's own container.** The first version of this ran ``psql -h 127.0.0.1``
    inside the postgres container and every login succeeded, including one with a
    deliberately wrong password -- the image's ``pg_hba.conf`` carries
    ``host all all 127.0.0.1/32 trust`` above its ``scram-sha-256`` line, so
    loopback is trusted exactly as the Unix socket is (D74). Only a connection
    arriving from another address reaches the line that checks a password, which
    is also the line dbmate's connection reaches.

    The password crosses on **stdin** and is read into a shell variable in the
    container. It is never an argument to ``docker`` or to ``psql``, never in the
    container's declared environment, and so appears in no process listing, no
    ``docker inspect`` and no log.
    """

    def login(
        document: dict[str, Any], network: str, role: str, password: str
    ) -> tuple[int, str, str]:
        # `export` on its own line rather than as a `VAR=v exec ...` prefix: a
        # prefix assignment to a special builtin persists in the shell but is not
        # required to be exported, and `exec` replaces that shell. `-w` so that a
        # rejected password fails instead of waiting on a prompt nobody answers.
        script = (
            'PGPASSWORD="$(cat)"; export PGPASSWORD; '
            'exec psql -h "$1" -p 5432 -U "$2" -d "$3" -w -X -qtA -c "SELECT 1"'
        )
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--interactive",
                "--network",
                network,
                "--entrypoint",
                "sh",
                _postgres_image(),
                "-c",
                script,
                "sh",
                # The service name, which is what resolves on the internal
                # network and what the dbmate entrypoint connects to. The
                # container name would not resolve: Compose names the container
                # and the network alias differently.
                "postgres",
                role,
                document["database"]["name"],
            ],
            input=password,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        return result.returncode, result.stdout, result.stderr

    return login


def _postgres_image() -> str:
    """The digest-pinned cluster image, reused as a client.

    The same image the cluster runs, so the client's libpq is the one the server
    was built against and a failure is about the credential rather than about a
    protocol version.
    """
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "POSTGRES_IMAGE":
            return value.strip()
    pytest.fail("POSTGRES_IMAGE is absent from versions.env")


# ---------------------------------------------------------------------------
# Session 4 — the two transports
# ---------------------------------------------------------------------------

#: Host-global port allocation state (ADR 0042).
PORT_REGISTRY = Path("/etc/agentic-postgres/database-port-allocations.json")


@pytest.fixture(scope="session")
def port_allocations(as_root: None) -> dict[str, Any]:
    """The host's port allocation registry, root-owned.

    Root-only rather than merely inconvenient: this file says which host port
    reaches which cluster, so a copy readable by anyone is a map of every
    database on the machine.
    """
    del as_root
    if not PORT_REGISTRY.is_file():
        pytest.fail(f"no port allocation registry at {PORT_REGISTRY}")
    return json.loads(PORT_REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def allocation_for(port_allocations: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    """One project's live allocation, refusing ambiguity the way the broker does.

    Searched by project key because the deployed document records no instance
    UUID (D106). Two live records for one key is a failure here for the same
    reason it is one in the broker: a first match would be a port reaching the
    wrong cluster, and every assertion downstream would still pass.
    """

    def find(project_key: str) -> dict[str, Any]:
        live = [
            allocation
            for allocation in port_allocations["allocations"]
            if allocation["project_key"] == project_key
            and allocation["state"] in ("reserved", "active")
        ]
        if not live:
            pytest.fail(f"{project_key} holds no live port allocation")
        if len(live) > 1:
            pytest.fail(f"{project_key} has {len(live)} live allocations; which cluster is unclear")
        return live[0]

    return find


@pytest.fixture(scope="session")
def materialized_secret() -> Callable[[str, str, str], str]:
    """One consumer's copy of one secret, from the generation the project points at.

    Per-consumer, because that is how they are written: ``pgbouncer``,
    ``dbmate`` and each client fixture hold *different files*. Reading the wrong
    one would prove a credential works for a service that was never given it.
    Through ``active-secret-generation.json`` rather than by listing
    ``generations/``, for the reason ``migration_password`` records.
    """

    def read(project_key: str, consumer: str, name: str) -> str:
        pointer = SECRET_ROOT / project_key / "active-secret-generation.json"
        if not pointer.is_file():
            pytest.fail(f"{project_key} has no active secret generation at {pointer}")
        generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
        path = SECRET_ROOT / project_key / "generations" / generation / consumer / name
        if not path.is_file():
            pytest.fail(f"generation {generation} of {project_key} has no {consumer}/{name}")
        value = path.read_text(encoding="utf-8").rstrip("\n")
        assert value, f"{path} is empty"
        return value

    return read


@pytest.fixture(scope="session")
def pooler_container(rendered_document: Callable[[str], dict[str, Any]]) -> Callable[[str], str]:
    """The pooler container's name, derived from the Compose project name.

    Derived rather than found by filtering on the image: two projects run the
    same pooler image, and a filter would return whichever container Docker
    listed first -- which is the shape of every cross-project mistake this suite
    exists to catch.
    """

    def name(project_key: str) -> str:
        return f"{rendered_document(project_key)['compose']['project_name']}-pgbouncer-1"

    return name


@pytest.fixture(scope="session")
def pool_console(pooler_container: Callable[[str], str]) -> Callable[[str, str], str]:
    """Run one statement against a project's pooler admin console.

    Inside the pooler's own container and through ``PGPASSFILE`` -- the 0600 file
    its entrypoint wrote into a tmpfs -- so the credential is never an argument,
    never in this process's environment, and never in ``docker inspect``. The
    same rule the health check follows, for the same reason.

    What comes back is read from the **running daemon**, not from the rendered
    ini. A file nobody loaded is exactly the kind of value that looks measured
    and is not.
    """

    def show(project_key: str, statement: str) -> str:
        script = (
            "PGPASSFILE=/etc/pgbouncer/.pgpass "
            'exec psql -h 127.0.0.1 -p "$APG_POOL_LISTEN_PORT" -U "$APG_POOL_ADMIN_USER" '
            f'-d pgbouncer -w -X -qtA -c "{statement}"'
        )
        result = subprocess.run(
            ["docker", "exec", pooler_container(project_key), "sh", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.fail(
                f"`{statement}` against {project_key}'s pooler exited {result.returncode}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result.stdout

    return show


@pytest.fixture(scope="session")
def pool_setting(pool_console: Callable[[str, str], str]) -> Callable[[str, str], str]:
    """One key from ``SHOW CONFIG``, read out of the running pooler."""

    def read(project_key: str, key: str) -> str:
        for line in pool_console(project_key, "SHOW CONFIG").splitlines():
            fields = line.split("|")
            if fields and fields[0].strip() == key:
                return fields[1].strip()
        pytest.fail(f"{project_key}'s pooler reports no setting named {key}")

    return read


@pytest.fixture(scope="session")
def compose_service(sh: Runner) -> Callable[[str, str], dict[str, Any]]:
    """One resolved Compose service definition from a project's installed model.

    Resolved through ``bin/compose.sh --runtime``, so what comes back is what the
    host would actually run: interpolated from ``compose.env`` and merged with
    the root-owned runtime and secret overrides. Reading ``compose.yaml`` out of
    the checkout instead would describe a model with no secrets attached and no
    publication, which is a different thing from the one running.
    """

    def read(project_key: str, service: str) -> dict[str, Any]:
        raw = sh(
            str(REPO_ROOT / "bin" / "compose.sh"),
            str(RENDERED_ROOT / project_key),
            "--runtime",
            "--profile",
            "session4-verify",
            "config",
            "--format",
            "json",
        )
        document = json.loads(raw)
        if service not in document["services"]:
            pytest.fail(f"{project_key}'s model has no service {service}")
        return document["services"][service]

    return read


@pytest.fixture(scope="session")
def client_image(
    sh: Runner, rendered_document: Callable[[str], dict[str, Any]]
) -> Callable[[str, str], str]:
    """Build one client fixture image and return its name.

    Used where a probe needs a *driver* rather than the fixture's own program --
    the pool tests drive Psycopg directly. Reusing the fixture's image rather
    than installing a driver at probe time means the driver under the probe is
    the one the committed hash-locked requirements pin, not whatever the index
    has today.
    """

    def build(project_key: str, service: str) -> str:
        sh(
            str(REPO_ROOT / "bin" / "compose.sh"),
            str(RENDERED_ROOT / project_key),
            "--profile",
            "session4-verify",
            "build",
            service,
        )
        return f"{rendered_document(project_key)['compose']['project_name']}-{service}"

    return build


@pytest.fixture(scope="session")
def run_client_fixture(
    sh: Runner,
    compose_service: Callable[[str, str], dict[str, Any]],
    rendered_document: Callable[[str], dict[str, Any]],
) -> Callable[..., tuple[int, str, str]]:
    """Build and run one client compatibility fixture. Returns, never judges.

    **Every input comes from the resolved Compose model** -- the environment, the
    user, the secret mount, the network. A harness that assembled its own
    environment would prove that *some* configuration works, and the
    configuration under test is the one in the model.

    ``docker run`` rather than ``docker compose run``, and that is not a
    shortcut: ``bin/compose.sh`` forbids ``run`` outright (D110), and a test is
    measuring rather than operating. Taking the model's own values as inputs is
    what keeps the service definitions from being decorative.
    """

    def run(project_key: str, service: str, *command: str) -> tuple[int, str, str]:
        rendered = rendered_document(project_key)
        definition = compose_service(project_key, service)

        sh(
            str(REPO_ROOT / "bin" / "compose.sh"),
            str(RENDERED_ROOT / project_key),
            "--profile",
            "session4-verify",
            "build",
            service,
        )

        arguments = [
            "docker",
            "run",
            "--rm",
            "--network",
            rendered["compose"]["networks"]["internal"],
            "--user",
            str(definition["user"]),
            "--read-only",
            # S108 does not apply: this is a tmpfs mount specification for a
            # container, not a path this process opens. The mount is private to
            # one container, 0700, and owned by the uid the model declares.
            "--tmpfs",
            "/tmp:rw,mode=0700,uid=65532,gid=65532",  # noqa: S108
        ]
        for key, value in sorted(definition.get("environment", {}).items()):
            arguments += ["--env", f"{key}={value}"]
        for volume in definition.get("volumes", []):
            arguments += ["--volume", f"{volume['source']}:{volume['target']}:ro"]
        arguments += [f"{rendered['compose']['project_name']}-{service}", *command]

        result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=300)
        return result.returncode, result.stdout, result.stderr

    return run
