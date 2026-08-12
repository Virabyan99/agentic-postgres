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

# ruff: noqa: S608
#
# Every statement below interpolates values that came from a deployed outputs
# document -- role names and a database name derived by `naming` and validated
# by the outputs schema -- plus fixed UUID constants declared in this file. None
# of it is operator input, and parameter binding is unavailable where an
# identifier, a role name or a `SET` target goes, which is the same reason
# `migrations.quote_identifier` exists. Suppressed per module rather than per
# line, as `tests/security/test_session3_authorization.py` does, because a wall
# of inline noqa comments is one nobody reads.
import dataclasses
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
def transport_login() -> Callable[..., tuple[int, str, str]]:
    """Attempt a password login over either transport. Returns, never judges.

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

    ``host`` and ``port`` are the service name and port on the project network --
    ``postgres:5432`` or ``pgbouncer:6432``. The container name would not
    resolve: Compose names the container and the network alias differently.
    """

    def login(
        document: dict[str, Any],
        network: str,
        role: str,
        password: str,
        *,
        host: str = "postgres",
        port: int = 5432,
    ) -> tuple[int, str, str]:
        # `export` on its own line rather than as a `VAR=v exec ...` prefix: a
        # prefix assignment to a special builtin persists in the shell but is not
        # required to be exported, and `exec` replaces that shell. `-w` so that a
        # rejected password fails instead of waiting on a prompt nobody answers.
        script = (
            'PGPASSWORD="$(cat)"; export PGPASSWORD; '
            'exec psql -h "$1" -p "$2" -U "$3" -d "$4" -w -X -qtA -c "SELECT 1"'
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
                host,
                str(port),
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


@pytest.fixture(scope="session")
def pg_login(
    transport_login: Callable[..., tuple[int, str, str]],
) -> Callable[[dict[str, Any], str, str, str], tuple[int, str, str]]:
    """The direct transport, which is what every Session 3 caller means.

    A wrapper rather than a second implementation. Session 4 needed the same
    login against ``pgbouncer:6432``, and the choice was to widen this signature
    at four call sites or to grow a second copy of the one piece of plumbing in
    this file that handles a credential. Two copies of that is two places for the
    password to stop crossing on stdin.
    """

    def login(
        document: dict[str, Any], network: str, role: str, password: str
    ) -> tuple[int, str, str]:
        return transport_login(document, network, role, password)

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
        definition = dict(document["services"][service])
        # The top-level secrets map, carried alongside. A service's `secrets:`
        # entry names a secret; only the top-level block says which file it is.
        # Run 9's first runner read the service's `volumes:` and nothing else,
        # so every fixture started with no credential mounted and exited 8
        # saying so -- a harness fault that reads exactly like a broken
        # materialization.
        definition["_secret_files"] = {
            name: entry.get("file") for name, entry in (document.get("secrets") or {}).items()
        }
        return definition

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

        # Compose mounts a declared secret at /run/secrets/<name>; `docker run`
        # has no such notion, so the grant surface is reconstructed here from
        # the model rather than assumed. Reconstructed from the MODEL, not from
        # the secret root: the point of running the fixture is to exercise what
        # the deploy actually granted it, and a path built here from a project
        # key would still mount a file when the grant had been removed.
        # `source` and `target` are two different names and using one for both
        # is how Run 9 mounted the right file where nobody was looking. `source`
        # is the namespaced secret -- `client-psql__app_runtime_password` --
        # which exists so two services' copies stay distinct in one top-level
        # block. `target` is the filename inside /run/secrets, and it is what
        # the container opens. Mounting at the source name produced a container
        # with its credential present, correct, and at a path its own entrypoint
        # had no reason to try.
        secret_files = definition.get("_secret_files", {})
        for entry in definition.get("secrets", []):
            name = entry["source"] if isinstance(entry, dict) else entry
            filename = entry.get("target", name) if isinstance(entry, dict) else name
            source = secret_files.get(name)
            if not source:
                pytest.fail(f"{service} is granted {name} and the model names no file for it")
            arguments += ["--volume", f"{source}:/run/secrets/{filename}:ro"]
        arguments += [f"{rendered['compose']['project_name']}-{service}", *command]

        result = subprocess.run(arguments, capture_output=True, text=True, check=False, timeout=300)
        return result.returncode, result.stdout, result.stderr

    return run


# ---------------------------------------------------------------------------
# Session 5 — the REST plane
# ---------------------------------------------------------------------------
#
# Session 5's security-marked proofs live in this directory rather than under
# tests/security/, which is D111's shape one session on: the marker decides what
# runs and what the evidence records, the directory decides which conftest is in
# scope, and everything below is what makes them measurable. The alternative was
# a second copy of "mint a token" and "call the route" in another directory, and
# a second copy of the one piece of plumbing that handles a credential is the
# thing D111 declined to grow.


@dataclasses.dataclass(frozen=True)
class ApiResponse:
    """One HTTP result, unjudged.

    ``status`` is ``0`` when nothing answered at all. That is a distinct value
    rather than an exception because the difference between "it refused" and
    "it was not there" is the whole content of several proofs below, and an
    assertion that only looks for the absence of a 200 cannot tell them apart
    (``bin/docs.py`` makes the same distinction for the same reason).
    """

    status: int
    headers: dict[str, str]
    body: str
    reason: str = ""


def _load_command(name: str, alias: str) -> Any:
    """Import one ``bin/*.py`` command as a module.

    The commands are not a package and are not on the path, which is deliberate:
    they are programs. Loading one here is how a test reuses the product's own
    logic instead of growing a second copy that is always the permissive one.
    """
    import importlib.util

    source = REPO_ROOT / "bin" / name
    specification = importlib.util.spec_from_file_location(alias, source)
    if specification is None or specification.loader is None:
        pytest.fail(f"cannot load {source}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def api_contract() -> Any:
    """``bin/api-contract.py``, loaded rather than reimplemented.

    Three pieces of logic that must not be duplicated. ``published_address``
    decides which host and base path a live document is normalized against, and
    a second copy would be the half that never learned a project's port is
    implicit when the URL names none. ``load_snapshot`` refuses non-canonical
    bytes and a real host, so a test reading the file with ``json.load`` would
    compare against a snapshot the command itself would reject. And
    ``surface_objects`` is the **one** place that spells a reviewed object the
    way a served path spells it -- ``notes`` and ``rpc/create_note``, not
    ``api.notes``. The two spellings are the reason this is a fixture rather
    than an import in one module: a comparison that mixed them would find every
    object missing from the other side, and the repair for that is always to
    loosen the comparison until it passes.
    """
    return _load_command("api-contract.py", "apg_api_contract_live")


@pytest.fixture(scope="session")
def dev_token() -> Any:
    """``bin/dev-token.py``, loaded as a module rather than reimplemented.

    The tests below need tokens the *command* refuses to mint -- one naming
    ``object_owner``, one naming a role of another project -- because a boundary
    is proved by attempting to cross it. What they must not do is grow a second
    idea of how a token is built: an algorithm, a ``kid``, an issuer or an
    audience assembled here would let every negative pass for the wrong reason,
    since a malformed token is refused by a service that would have accepted a
    well-formed one just as happily.

    So the enumeration stays in the command, where an operator meets it, and the
    construction comes from here, where it is the product's own.
    """
    return _load_command("dev-token.py", "apg_dev_token")


@pytest.fixture(scope="session")
def docs_command() -> Any:
    """``bin/docs.py``, so ``check``'s definition of a refusal is not restated.

    ``check`` returns 0 only on a 401 carrying a ``Basic`` challenge, and reports
    an unreachable route as unreachable rather than as refusing. Reimplementing
    that would produce a second definition, and the second one is always the
    permissive one: "not a 200" is satisfied by a route that does not exist.
    """
    return _load_command("docs.py", "apg_docs_live")


@pytest.fixture(scope="session")
def mint_token(dev_token, as_root: None) -> Callable[..., str]:
    """Sign a token for one project. The return value is a credential.

    Root, because the signing key is 0400 owned by root -- which is the property
    ``SEC-BOOT-001`` proves and this fixture depends on rather than works around.
    The key is located through the *deployed document's* generation, not the
    live pointer: D76: the pointer moves at the first restart, and signing with
    a key the running service does not verify against would produce a 401 that
    reads exactly like a boundary working.
    """
    del as_root

    def sign(document: dict[str, Any], role_name: str, *, subject: str | None, ttl: int = 300):
        key = dev_token.signing_key_path(document["project"]["key"], document)
        return dev_token.mint(
            key_path=key, role_name=role_name, subject=subject, ttl=ttl, document=document
        )

    return sign


@pytest.fixture(scope="session")
def request_subject(dev_token) -> Callable[[str], str]:
    """The per-project development subject, derived the way the command derives it."""

    def derive(project_key: str) -> str:
        return dev_token.development_subject(project_key)

    return derive


@pytest.fixture(scope="session")
def rest_base() -> Callable[[dict[str, Any]], str]:
    """One project's published REST prefix, with no trailing slash.

    From ``routes.rest`` and only when it says ``ready``. A project deployed
    through any session before 5 records ``unavailable`` there, and a test that
    fell back to composing a URL from the domain would send its requests to a
    hostname with no REST router behind it -- where every negative assertion
    would pass against a 404.
    """

    def base(document: dict[str, Any]) -> str:
        route = ((document.get("routes") or {}).get("rest")) or {}
        if route.get("status") != "ready" or not route.get("url"):
            pytest.fail(
                f"{document['project']['key']} publishes no ready REST route, so there "
                "is no surface here to measure"
            )
        return str(route["url"]).rstrip("/")

    return base


@pytest.fixture(scope="session")
def api_call() -> Callable[..., ApiResponse]:
    """Make one HTTP request and report what came back. Never judges.

    A raised exception on a 4xx would make every negative proof below a
    ``pytest.raises``, and the interesting part of a refusal is its status, its
    body and whether it named anything internal -- all of which an exception
    would have to be unpacked for anyway.
    """

    def call(
        url: str,
        *,
        method: str = "GET",
        token: str | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=payload, method=method)  # noqa: S310
        request.add_header("Accept", "application/json")
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, value)

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return ApiResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read().decode("utf-8", "replace"),
                )
        except urllib.error.HTTPError as error:
            return ApiResponse(
                status=error.code,
                headers=dict(error.headers.items()),
                body=error.read().decode("utf-8", "replace"),
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            return ApiResponse(
                status=0, headers={}, body="", reason=f"{type(error).__name__}: {error}"
            )

    return call


@pytest.fixture(scope="session")
def psql() -> Callable[..., tuple[int, str, str]]:
    """Run one statement over the cluster's container socket. Returns, never judges.

    ``docker exec -i``, and the ``-i`` matters: without it stdin is not
    forwarded, psql reads nothing, and the command exits 0 having executed
    nothing -- a silent success indistinguishable from a real one, and the trap
    ``CLAUDE.md`` records having cost time twice.

    ``role`` and ``claim`` are prepended rather than passed as parameters
    because neither an identifier nor a ``SET`` target can be bound; it is the
    same reason ``migrations.quote_identifier`` exists. Every value that reaches
    them here comes from a deployed document the outputs schema validated.
    """

    def run(
        document: dict[str, Any],
        statement: str,
        *,
        role: str | None = None,
        claim: str | None = None,
        timeout: int = 180,
    ) -> tuple[int, str, str]:
        prelude = ""
        if role is not None:
            prelude += f'SET ROLE "{role}"; '
        if claim is not None:
            prelude += f"SET app.user_id = '{claim}'; "
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                document["database"]["container"],
                "psql",
                "-U",
                "postgres",
                "-d",
                document["database"]["name"],
                "-X",
                "-qtA",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                prelude + statement,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()

    return run


#: The probe subject. A fixed UUID that is nobody's development subject, so the
#: rows it owns are attributable and cannot be confused with a real caller's --
#: and so that a teardown deleting by owner cannot delete anything else.
PROBE_SUBJECT = "00000000-5e55-4100-8000-0000000f8b1e"

#: How long PostgREST may take to act on `NOTIFY pgrst, 'reload schema'` before
#: the fixture calls it a failure rather than a delay. Generous on purpose: the
#: number is a ceiling on a notification round trip, and every observed reload
#: on this host has completed well inside a second. A fixture that waited
#: forever would turn a dead channel into a hung suite.
PROBE_RELOAD_TIMEOUT_SECONDS = 30.0


@pytest.fixture(scope="module")
def acceptance_probe(
    project_a: dict[str, Any],
    psql: Callable[..., tuple[int, str, str]],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    mint_token: Callable[..., str],
) -> Any:
    """The transient acceptance object and its rows (plan §4.4).

    Two things the released schema deliberately does not have: a function slow
    enough to exceed a request role's ``statement_timeout``, and more rows than
    ``api.max_rows`` under one owner. Both are needed to prove a limit is
    *enforced* rather than merely configured, and neither may be left behind.

    Owned by the object owner and executable only by ``authenticated``, so the
    probe cannot widen what any other role can reach while it exists. Created
    and dropped with a ``NOTIFY`` on each side, because PostgREST would
    otherwise serve a cached schema that either lacks the function or still
    advertises it.

    **Inside the project's deployment lock**, which is what §4.4 asks for and
    what ``rendering.project_lock`` already is. The lock is non-blocking: a
    deploy in flight makes this fixture fail rather than let a probe object
    exist in ``api`` while a snapshot is being captured from the same cluster.
    That is the one interleaving that would put the probe in a *reviewed*
    artifact rather than merely in a running one.

    **A cleanup failure is a failure, not a warning.** The teardown asserts the
    function is gone and the rows are gone, and an object left in ``api`` is on
    the published surface -- which is why ``API-SCHEMA-001`` and
    ``API-CONTRACT-001`` both check for this name independently, in a state
    where this fixture is not running.
    """
    from agentic_postgres.rendering import ACCEPTANCE_PROBE_FUNCTION, project_lock

    roles = project_a["database"]["roles"]
    owner, caller = roles["object_owner"], roles["authenticated"]
    max_rows = (project_a.get("api") or {}).get("max_rows")
    if not isinstance(max_rows, int):
        pytest.fail(
            "the deployed document records no api.max_rows, so there is no ceiling "
            "here to exceed and the row-limit proof would measure nothing"
        )
    surplus = max_rows + 1
    qualified = f"api.{ACCEPTANCE_PROBE_FUNCTION}"

    def must(statement: str, *, role: str | None = None, claim: str | None = None) -> str:
        status, out, err = psql(project_a, statement, role=role, claim=claim)
        if status != 0:
            pytest.fail(f"`{statement.splitlines()[0]}` failed: {err}")
        return out

    # The lock is taken before the CREATE, not around the yield. A deploy that
    # interleaved with the creation is the one that could capture a snapshot
    # while the probe is in `api` -- which would put it in a *reviewed* artifact
    # rather than merely in a running cluster.
    with project_lock(project_a["project"]["key"]):
        must(
            f"CREATE FUNCTION {qualified}(p_seconds double precision) "
            "RETURNS double precision LANGUAGE sql VOLATILE "
            "SET search_path = pg_catalog, pg_temp "
            "AS $probe$ SELECT p_seconds FROM pg_catalog.pg_sleep(p_seconds) $probe$; "
            f"REVOKE ALL ON FUNCTION {qualified}(double precision) FROM PUBLIC; "
            f'GRANT EXECUTE ON FUNCTION {qualified}(double precision) TO "{caller}";',
            role=owner,
        )
        inserted = must(
            "WITH added AS ("
            "INSERT INTO app.notes (owner_id, title, content) "
            f"SELECT '{PROBE_SUBJECT}'::uuid, 'apg-probe-' || g, '' "
            f"FROM generate_series(1, {surplus}) g RETURNING 1) SELECT count(*) FROM added;",
            role=owner,
            claim=PROBE_SUBJECT,
        )
        # Asserted rather than assumed: an INSERT against a FORCE RLS table whose
        # policy claim is absent matches nothing and reports success, which is the
        # shape that made a migration's UPDATE silently do nothing (CLAUDE.md §6).
        if inserted != str(surplus):
            must(
                f"DELETE FROM app.notes WHERE owner_id = '{PROBE_SUBJECT}';",
                role=owner,
                claim=PROBE_SUBJECT,
            )
            must(f"DROP FUNCTION IF EXISTS {qualified}(double precision);", role=owner)
            pytest.fail(f"seeded {inserted} probe rows, expected {surplus}")

        must("NOTIFY pgrst, 'reload schema';")

        # NOTIFY is asynchronous, and the fixture used to yield straight after
        # it. Every consumer then called the probe RPC before PostgREST had
        # rebuilt its cache and got `404 Could not find the function
        # api.apg_acceptance_probe(p_seconds) in the schema cache` -- a race, not
        # a boundary, and one that reads exactly like an RPC that was never
        # created (D193).
        #
        # **Polled through the REST plane, not the catalog.** The catalog has the
        # function the instant the CREATE commits, so a `pg_proc` query would
        # succeed immediately and wait for nothing; the thing that lags is
        # PostgREST's schema cache, and the only place that is visible is a
        # request. Waiting here rather than in each consumer also turns the
        # reload into an assertion: if the function never becomes callable, the
        # notification channel is not delivering, which is a finding about
        # `db-channel-enabled` rather than a slow fixture.
        probe_base = rest_base(project_a)
        probe_token = mint_token(project_a, caller, subject=PROBE_SUBJECT)
        deadline = time.monotonic() + PROBE_RELOAD_TIMEOUT_SECONDS
        last = None
        while time.monotonic() < deadline:
            answer = api_call(
                f"{probe_base}/rpc/{ACCEPTANCE_PROBE_FUNCTION}",
                method="POST",
                token=probe_token,
                body={"p_seconds": 0},
            )
            last = answer
            if answer.status != 404:
                break
            time.sleep(0.5)
        else:
            # Same cleanup the seed-count failure above performs. A fixture that
            # fails without removing what it created leaves an object in `api`,
            # which is on the published surface.
            psql(
                project_a,
                f"DELETE FROM app.notes WHERE owner_id = '{PROBE_SUBJECT}';",
                role=owner,
                claim=PROBE_SUBJECT,
            )
            psql(project_a, f"DROP FUNCTION IF EXISTS {qualified}(double precision);", role=owner)
            psql(project_a, "NOTIFY pgrst, 'reload schema';")
            pytest.fail(
                f"{qualified} was still 404 after {PROBE_RELOAD_TIMEOUT_SECONDS}s "
                f"(last body: {(last.body if last else '')[:200]!r}). The schema cache "
                "never picked up the CREATE, so `db-channel-enabled` is not delivering"
            )

        try:
            yield {
                "function": ACCEPTANCE_PROBE_FUNCTION,
                "qualified": qualified,
                "subject": PROBE_SUBJECT,
                "max_rows": max_rows,
                "seeded_rows": surplus,
            }
        finally:
            _, dropped, drop_error = psql(
                project_a, f"DROP FUNCTION IF EXISTS {qualified}(double precision);", role=owner
            )
            _, _, delete_error = psql(
                project_a,
                f"DELETE FROM app.notes WHERE owner_id = '{PROBE_SUBJECT}';",
                role=owner,
                claim=PROBE_SUBJECT,
            )
            psql(project_a, "NOTIFY pgrst, 'reload schema';")

            _, remaining, _ = psql(
                project_a,
                "SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'api' AND p.proname = "
                f"'{ACCEPTANCE_PROBE_FUNCTION}';",
            )
            _, rows, _ = psql(
                project_a,
                f"SELECT count(*) FROM app.notes WHERE owner_id = '{PROBE_SUBJECT}';",
                role=owner,
                claim=PROBE_SUBJECT,
            )
            assert remaining == "0", (
                f"{qualified} survived teardown ({dropped} {drop_error}); it is on the "
                "published surface until somebody removes it by hand"
            )
            assert rows == "0", f"{rows} probe rows survived teardown ({delete_error})"
