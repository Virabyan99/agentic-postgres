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
