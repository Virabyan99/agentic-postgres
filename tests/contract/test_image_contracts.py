"""What the locked database images actually are (Session 3 §3.2, Session 4 §3.2).

Numbers the runbooks tell us to assume, measured instead. This module is the
only place their values are written down, which is why it runs against the
locked digests rather than against a tag: a fact recorded here and a fact
recorded in prose diverge the first time an image is rebuilt, and only one of
them fails a test.

Each of the three has already burned this repository once in a neighbouring
form, and each was wrong in a different way than expected:

* the **UID/GID** is 999, not the 65532 every Session 2 consumer uses, and the
  container's default user is not the server's user -- the entrypoint starts as
  root and drops privilege. `secrets.required.yaml` names 999 because the
  service runs as 999.
* **PGDATA** is `/var/lib/postgresql/18/docker`, but the image declares its
  VOLUME on the *parent*. The plan predicted that a wrong mount target
  "initialises into an anonymous volume and loses everything on recreate". It
  does not: the pre-18 path makes the image refuse to start outright, and
  mounting at PGDATA itself works while leaving a stray anonymous volume. Two
  of the three candidates persist data, so persistence is the one property that
  cannot tell them apart. See D53.
* the **dbmate flags** are all accepted, but not in one position: three are
  global-only and `--strict` is subcommand-only and absent from `status`.

Session 4 added three more, and two of them contradicted the runbook:

* the **pooler's UID is 70**, a third number after the cluster's 999 and Session
  2's 65532, and its image *does* set a default user -- so unlike the cluster it
  never runs as root and never drops privilege. A secret file owned 999 or
  65532 would be unreadable by it.
* the locked pooler is **1.24.1**, not the 1.25.2 the runbook called a minimum
  security baseline, and it does everything Session 4 needs: named prepared
  statements survive a backend change when tracking is on, and demonstrably do
  not when it is off. The floor stayed where it was because a measurement said
  so (D98).
* a **published loopback port does not match the trust line**. This is the one
  that would have been catastrophic to assume: see the test at the bottom of
  this module, and note that it asserts the control as well as the result.

Session 5 added four, and the runbook was wrong about three of them:

* the PostgREST image is **distroless** -- no shell, no wget, no curl. A
  healthcheck can therefore be neither ``CMD-SHELL`` nor an HTTP probe, and the
  only thing that can look from inside the container is the binary itself. That
  single fact is what forced the version bump.
* **``postgrest --ready`` exists in 14.16 and not in 13.0.4**, which is why the
  bump happened; and it **returns 0 while every request is failing**, which is
  why it cannot be the whole healthcheck. It asks the admin server about the
  pool and the schema cache. A service whose pre-request hook does not resolve
  is refusing every request and is, by that probe, ready. This is D101's pooler
  one session on: a listening port is not a working service, and now neither is
  a green readiness endpoint.
* **``client-error-verbosity`` exists in neither 13.0.4 nor 14.16.** The runbook
  sets it in its required configuration baseline and asserts it in its gate; it
  arrives in 16.0. A key read from documentation for a version that does not
  have it is ADR 0019 exactly, in the runbook's own §11.3.
* the **PGRST error shape is the other way round** from the runbook's: the
  response body is the JSON in ``MESSAGE`` and the status and headers are the
  JSON in ``DETAIL``. Following the runbook produces ``PGRST121`` and **HTTP
  500** where a 401 was intended, so the difference is not cosmetic.

Run 3 measured the admin surface and the probe that reads it, against a real
cluster, and both answers were the opposite of what had been assumed:

* **the admin server binds whatever the public server binds.** With
  ``server-host = "0.0.0.0"`` -- which every containerised service needs -- and
  only ``admin-server-port`` set, ``/live`` and ``/ready`` answered a peer
  container on the project network. ``admin-server-host = "127.0.0.1"`` refuses
  that peer and leaves ``--ready`` working. The admin surface is loopback-only
  when it is told to be, and not before.
* **``postgrest --ready`` is a client that reads its own configuration**, not
  the running process's. Bare, it exits 1 with *"Admin server is not running"*
  against a service answering 200. It needs the config file as an argument, or
  both ``PGRST_ADMIN_SERVER_HOST`` and ``PGRST_ADMIN_SERVER_PORT`` -- the port
  alone is refused, because the default host is a wildcard and it will not probe
  one. So the obvious healthcheck fails on a healthy container, which is D145
  arriving from the other direction.

And the measurement that closes Run 1's deferred item: **the JWKS file is
genuinely loaded**, proved by three distinguishable answers rather than by the
container not crashing. A token signed with the key returns 200; the same token
against a different key set returns ``PGRST301`` *"No suitable key was found"*;
a token signed by another key returns ``PGRST301`` *"None of the keys was able
to decode the JWT"*. **A JWKS carrying ``d`` was accepted and served** --
PostgREST does not refuse private material, so ``jwt_keys.assert_public`` is the
only thing between a signing key and a published verification set.

Marked `database` rather than `contract`: these need a container runtime, and
the Session 1 gate's `-m "contract and not future"` selection must stay
runnable in a checkout. A runner without Docker reports that it could not look,
never a verdict (ADR 0018).
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, runtime_override

pytestmark = [pytest.mark.database, pytest.mark.p0]

#: Measured against the locked digests. Changing any of these is changing a
#: fact about an image, which means the lock moved -- so it belongs in the same
#: commit as a `bin/lock-versions.sh --update`, not in a fix-up.
POSTGRES_UID = 999
POSTGRES_GID = 999
#: Imported rather than restated since Session 10 (D514).
#:
#: These were literals here, and that was right while this module was their only
#: reader. Session 10 gave PGDATA a second one -- `pgbackrest.conf`'s `pg1-path`
#: -- and two literals would be two authorities for a path whose disagreement
#: does not fail: a stanza created against the mount point instead of PGDATA
#: restores the wrong thing rather than erroring. Importing makes the
#: measurement below a measurement of the value the renderer actually writes.
POSTGRES_PGDATA = runtime_override.POSTGRES_PGDATA
POSTGRES_VOLUME_TARGET = runtime_override.POSTGRES_VOLUME_TARGET
POSTGRES_MAJOR = "18"
PGVECTOR_VERSION = "0.8.6"

#: dbmate 2.34.1 splits its flags across two positions. Wrong position is
#: `exit 2` with "flag provided but not defined", which is loud; a global flag
#: silently omitted writes the ledger somewhere else, which is not.
DBMATE_GLOBAL_FLAGS = ("--migrations-dir", "--migrations-table", "--no-dump-schema", "--env-file")
DBMATE_SUBCOMMAND_FLAGS = {"up": ("--strict",), "migrate": ("--strict",)}
#: `status` has `--exit-code` and `--quiet` and NOT `--strict`. Recorded as an
#: absence because a command built by analogy with `up` would pass `--strict`
#: to `status` and fail every run.
DBMATE_SUBCOMMANDS_WITHOUT_STRICT = ("status",)

#: Measured against the locked pooler digest, Session 4 Run 1.
PGBOUNCER_VERSION = "1.24.1"
#: A third UID, and the one place it differs structurally from the cluster: the
#: pooler image sets a default user, so the process never starts as root.
PGBOUNCER_UID = 70
PGBOUNCER_GID = 70
PGBOUNCER_DEFAULT_USER = "postgres"
#: The image's own default listen port, which is NOT the 6432 convention. The
#: project renders 6432 explicitly; a health check written against the
#: convention rather than against the rendered value would probe the wrong port
#: on a default-configured container.
PGBOUNCER_IMAGE_DEFAULT_PORT = 5432
#: The readiness check needs a client and the image has one. Assuming a
#: third-party image's contents is how a health check becomes a health claim.
PGBOUNCER_CLIENT_TOOLS = ("psql", "pg_isready")
PGBOUNCER_PSQL_MAJOR = "17"
PGBOUNCER_CONFIG_DIR = "/etc/pgbouncer"


def _lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / "versions.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


LOCK = _lock()


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(["docker", "info"], capture_output=True, text=True, check=False).returncode
        == 0
    )


#: ADR 0018: a check that cannot reach the daemon reports that, not a verdict.
requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="the Docker daemon is unreachable, so no image can be measured"
)


def run(*args: str, image: str, via_sh: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the image's own entrypoint, or a shell inside it.

    ``via_sh=True`` needs the explicit ``-c``: `--entrypoint sh` followed by a
    bare string makes sh treat it as a *filename*, which fails with "cannot
    open" and an exit code that is not the one under test.

    Named ``via_sh`` rather than ``shell`` because ruff's S604 reads any
    ``shell=True`` keyword as ``subprocess``'s own. Silencing a real security
    rule to keep a nicer parameter name is the wrong trade, and nothing here
    runs through a host shell: the argument list goes to ``docker`` directly
    and the ``sh`` is the one inside the container.
    """
    command = ["docker", "run", "--rm", "--platform", "linux/amd64"]
    if via_sh:
        command += ["--entrypoint", "sh", image, "-c", *args]
    else:
        command += [image, *args]
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=180)


@pytest.fixture(scope="module")
def postgres_image() -> str:
    image = LOCK["POSTGRES_IMAGE"]
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "-q", image],
        capture_output=True,
        check=False,
        timeout=600,
    )
    return image


@pytest.fixture(scope="module")
def dbmate_image() -> str:
    image = LOCK["DBMATE_IMAGE"]
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "-q", image],
        capture_output=True,
        check=False,
        timeout=600,
    )
    return image


@pytest.fixture(scope="module")
def postgres_config(postgres_image: str) -> dict:
    result = subprocess.run(
        ["docker", "image", "inspect", postgres_image],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)[0]


# ---------------------------------------------------------------------------
# The images are the locked ones
# ---------------------------------------------------------------------------


def test_both_images_are_digest_pinned() -> None:
    """Offline. A tag is not a lock, and this runs without a daemon."""
    for key in ("POSTGRES_IMAGE", "DBMATE_IMAGE", "PGBOUNCER_IMAGE"):
        assert "@sha256:" in LOCK[key], f"{key} is not digest-pinned: {LOCK[key]}"


# ---------------------------------------------------------------------------
# UID / GID
# ---------------------------------------------------------------------------


@requires_docker
def test_the_postgres_user_is_the_measured_uid(postgres_image: str) -> None:
    result = run("id -u postgres; id -g postgres", image=postgres_image, via_sh=True)
    assert result.returncode == 0, result.stderr
    uid, gid = (int(line) for line in result.stdout.split())
    assert (uid, gid) == (POSTGRES_UID, POSTGRES_GID)


@requires_docker
def test_the_default_container_user_is_not_the_server_user(postgres_config: dict) -> None:
    """The distinction that makes the secret's ownership non-obvious.

    `Config.User` is empty, so a container started without `user:` runs as root
    and the entrypoint gosu's down to postgres. Reading the image's default
    user to decide who must own a secret file would give 0, and a secret owned
    by root mode 0400 is unreadable by the process that actually needs it once
    privilege is dropped.
    """
    # `.get`, not `[...]`: Docker omits the key entirely rather than emitting
    # an empty string, so indexing would raise KeyError on the very case this
    # asserts -- a failure that reads like a broken test rather than a finding.
    assert postgres_config["Config"].get("User") in ("", None)


def test_the_compose_service_runs_as_the_measured_uid() -> None:
    """Offline. The model and the measurement must name the same numbers."""
    import yaml

    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert model["services"]["postgres"]["user"] == f"{POSTGRES_UID}:{POSTGRES_GID}"


def test_the_secret_contract_names_the_measured_uid() -> None:
    """Offline. The third place the same two numbers appear."""
    import yaml

    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    consumers = [
        consumer
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
        if consumer.get("service") == "postgres"
    ]
    assert consumers, "no secret is granted to the postgres service"
    for consumer in consumers:
        assert (consumer["uid"], consumer["gid"]) == (POSTGRES_UID, POSTGRES_GID)


# ---------------------------------------------------------------------------
# PGDATA and the mount target (D53)
# ---------------------------------------------------------------------------


@requires_docker
def test_pgdata_is_where_it_was_measured(postgres_config: dict) -> None:
    environment = dict(
        item.split("=", 1) for item in postgres_config["Config"]["Env"] if "=" in item
    )
    assert environment["PGDATA"] == POSTGRES_PGDATA
    assert environment["PG_MAJOR"] == POSTGRES_MAJOR


@requires_docker
def test_the_declared_volume_is_the_parent_of_pgdata(postgres_config: dict) -> None:
    """The fact the whole mount decision turns on.

    The image declares its VOLUME on `/var/lib/postgresql` while PGDATA is a
    directory *inside* it. Mounting the named volume at PGDATA therefore leaves
    the parent to an anonymous volume, which persists data and accumulates a
    stray volume per container -- the configuration that works and is wrong.
    """
    declared = set(postgres_config["Config"]["Volumes"] or {})
    assert declared == {POSTGRES_VOLUME_TARGET}
    assert POSTGRES_PGDATA.startswith(POSTGRES_VOLUME_TARGET + "/")
    assert POSTGRES_PGDATA != POSTGRES_VOLUME_TARGET


def test_the_model_mounts_the_declared_volume_not_pgdata() -> None:
    """Offline, and the assertion that would have caught the runbook's path.

    Checked as an exact mount target rather than as "the data survives",
    because two of the three candidate targets persist data and only one of
    them leaves a single mount.
    """
    import yaml

    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    for name, service in model["services"].items():
        for mount in service.get("volumes", []):
            if not str(mount).startswith("postgres-data:"):
                continue
            target = str(mount).split(":", 1)[1]
            assert target == POSTGRES_VOLUME_TARGET, (
                f"service {name} mounts the postgres volume at {target}; "
                f"the image declares {POSTGRES_VOLUME_TARGET} and PGDATA is inside it"
            )


def test_the_postgres_service_has_exactly_one_volume() -> None:
    """A second mount is how the anonymous-volume configuration would arrive."""
    import yaml

    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert model["services"]["postgres"]["volumes"] == [f"postgres-data:{POSTGRES_VOLUME_TARGET}"]


# ---------------------------------------------------------------------------
# pgvector (DBX-PG-001's offline half)
# ---------------------------------------------------------------------------


@requires_docker
def test_pgvector_is_present_at_the_locked_version(postgres_image: str) -> None:
    """Read from the control file, which is what `CREATE EXTENSION` resolves.

    The installed version is a live claim and belongs to DBX-PG-001 on the
    host. What is provable here is that the image ships it at all and at which
    default version -- an image without pgvector would otherwise fail for the
    first time during bootstrap on the host.
    """
    result = run(
        f"cat /usr/share/postgresql/{POSTGRES_MAJOR}/extension/vector.control",
        image=postgres_image,
        via_sh=True,
    )
    assert result.returncode == 0, result.stderr
    assert f"default_version = '{PGVECTOR_VERSION}'" in result.stdout


@requires_docker
def test_the_server_major_version_matches_the_lock(postgres_image: str) -> None:
    result = run("postgres --version", image=postgres_image, via_sh=True)
    assert result.returncode == 0, result.stderr
    assert f"(PostgreSQL) {POSTGRES_MAJOR}." in result.stdout


# ---------------------------------------------------------------------------
# dbmate flag positions
# ---------------------------------------------------------------------------


@requires_docker
@pytest.mark.parametrize("flag", DBMATE_GLOBAL_FLAGS)
def test_global_flags_are_rejected_after_the_subcommand(dbmate_image: str, flag: str) -> None:
    """The half of the contract that is an absence.

    A command built by putting every flag after the subcommand -- which is how
    most CLIs work -- exits 2 here. Asserting the rejection is what stops the
    Compose command being 'fixed' by moving a flag.
    """
    result = run("status", flag, "x", image=dbmate_image)
    assert result.returncode == 2
    assert "flag provided but not defined" in (result.stdout + result.stderr)


@requires_docker
@pytest.mark.parametrize("flag", DBMATE_GLOBAL_FLAGS)
def test_global_flags_are_accepted_before_the_subcommand(dbmate_image: str, flag: str) -> None:
    """Accepted means "parsed", not "succeeded": there is no database here.

    The distinction matters. Both positions exit non-zero, so a test that only
    checked for failure would pass on the broken ordering too.
    """
    result = run(flag, "x", "status", image=dbmate_image)
    output = result.stdout + result.stderr
    assert "flag provided but not defined" not in output, output


@requires_docker
@pytest.mark.parametrize(
    ("subcommand", "flag"),
    [(sub, flag) for sub, flags in DBMATE_SUBCOMMAND_FLAGS.items() for flag in flags],
)
def test_subcommand_flags_are_accepted_after_their_subcommand(
    dbmate_image: str, subcommand: str, flag: str
) -> None:
    result = run(subcommand, flag, image=dbmate_image)
    output = result.stdout + result.stderr
    assert "flag provided but not defined" not in output, output


@requires_docker
@pytest.mark.parametrize("subcommand", DBMATE_SUBCOMMANDS_WITHOUT_STRICT)
def test_strict_does_not_exist_on_every_subcommand(dbmate_image: str, subcommand: str) -> None:
    """`--strict` is on `up` and `migrate` and not on `status`.

    Recorded because the natural mistake is to apply it uniformly, and the
    result is a preflight that exits 2 on every invocation.
    """
    result = run(subcommand, "--strict", image=dbmate_image)
    assert result.returncode == 2
    assert "flag provided but not defined" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# The runtime base image agrees with the locked Python (D99)
# ---------------------------------------------------------------------------


@requires_docker
def test_the_runtime_base_image_carries_the_locked_python() -> None:
    """Found by accident in Session 4 Run 1, and it is this project's own pattern.

    `PYTHON_RUNTIME_IMAGE` selects the rolling tag `3.12-slim`, so re-locking
    resolves whatever that tag points at today -- it moved digests between two
    runs three days apart. `versions.env` separately asserts
    `PYTHON_VERSION=3.12.13` and `--check` compares that against
    `.python-version`, so the *repository's* Python is pinned to a patch while
    the image every first-party service is built FROM is pinned only to a minor.

    Nothing compared the two. They agree today, which is exactly how long a
    wrong answer coincides with the right one: the next 3.12.x tag push moves
    the container's interpreter and no check in this repository notices.
    """
    image = LOCK["PYTHON_RUNTIME_IMAGE"]
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "-q", image],
        capture_output=True,
        check=False,
        timeout=600,
    )
    result = run("python --version", image=image, via_sh=True)
    assert result.returncode == 0, result.stderr
    reported = result.stdout.strip()
    assert reported == f"Python {LOCK['PYTHON_VERSION']}", (
        f"the runtime base image reports {reported!r} but versions.env locks "
        f"PYTHON_VERSION={LOCK['PYTHON_VERSION']}; the rolling tag moved"
    )


# ---------------------------------------------------------------------------
# The locked pooler (Session 4 plan §3.2, D85)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pgbouncer_image() -> str:
    image = LOCK["PGBOUNCER_IMAGE"]
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "-q", image],
        capture_output=True,
        check=False,
        timeout=600,
    )
    return image


@pytest.fixture(scope="module")
def pgbouncer_config(pgbouncer_image: str) -> dict:
    result = subprocess.run(
        ["docker", "image", "inspect", pgbouncer_image],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)[0]


@requires_docker
def test_the_pooler_reports_the_measured_version(pgbouncer_image: str) -> None:
    """The runbook asked for >= 1.25.2 on the strength of a changelog.

    ADR 0019 is the standing lesson about floors read from documentation. The
    version recorded here is the one the locked digest reports, and the two
    behavioural tests below are why it was kept rather than bumped.
    """
    result = run("pgbouncer --version", image=pgbouncer_image, via_sh=True)
    assert result.returncode == 0, result.stderr
    assert f"PgBouncer {PGBOUNCER_VERSION}" in result.stdout, result.stdout


@requires_docker
def test_the_pooler_image_carries_a_client_the_readiness_check_can_use(
    pgbouncer_image: str,
) -> None:
    """A health check that shells out to a tool the image lacks is a health claim."""
    result = run(
        "for t in psql pg_isready; do command -v $t || echo ABSENT-$t; done; psql --version",
        image=pgbouncer_image,
        via_sh=True,
    )
    assert result.returncode == 0, result.stderr
    for tool in PGBOUNCER_CLIENT_TOOLS:
        assert f"ABSENT-{tool}" not in result.stdout, f"{tool} is not in the pooler image"
    assert f"psql (PostgreSQL) {PGBOUNCER_PSQL_MAJOR}." in result.stdout, result.stdout


@requires_docker
def test_the_pooler_runs_as_the_measured_uid(pgbouncer_image: str, pgbouncer_config: dict) -> None:
    """Third UID in this system, and the one that behaves unlike the cluster's.

    The cluster image leaves `Config.User` empty and drops privilege in its
    entrypoint. This one sets a user, so the process is 70 from PID 1 onward and
    there is no root window in which to fix up a file's ownership. A secret
    granted to the pooler must be readable by 70 at the moment it is mounted.
    """
    assert pgbouncer_config["Config"]["User"] == PGBOUNCER_DEFAULT_USER
    result = run("id -u; id -g", image=pgbouncer_image, via_sh=True)
    assert result.returncode == 0, result.stderr
    uid, gid = (int(line) for line in result.stdout.split())
    assert (uid, gid) == (PGBOUNCER_UID, PGBOUNCER_GID)


@requires_docker
def test_the_pooler_image_default_port_is_not_the_convention(pgbouncer_config: dict) -> None:
    """Recorded as a trap rather than as a preference.

    6432 is the PgBouncer convention and what this project renders. The image
    exposes and defaults to 5432, so a probe written against the convention would
    pass or fail for reasons unrelated to the pooler being healthy.
    """
    exposed = set(pgbouncer_config["Config"].get("ExposedPorts") or {})
    assert exposed == {f"{PGBOUNCER_IMAGE_DEFAULT_PORT}/tcp"}, exposed


@requires_docker
def test_the_pooler_entrypoint_generates_a_config_only_when_none_is_mounted(
    pgbouncer_image: str,
) -> None:
    """Why this project mounts a rendered INI instead of using the image's API.

    The image's documented interface is `DATABASE_URL`, from which the entrypoint
    parses a password and writes it into the user list. Its own comment says
    `docker inspect` will show it. That is forbidden here -- no secret value may
    enter Compose interpolation or process arguments -- so the whole interface is
    unusable, and what makes avoiding it possible is the guard asserted below:
    an INI that already exists is left alone.
    """
    result = run("cat /entrypoint.sh", image=pgbouncer_image, via_sh=True)
    assert result.returncode == 0, result.stderr
    entrypoint = result.stdout

    assert "DATABASE_URL" in entrypoint, (
        "the environment-variable credential interface is gone; if the image no "
        "longer generates a config from it, re-measure before relying on the guard below"
    )
    assert '[ ! -f "${PG_CONFIG_FILE}" ]' in entrypoint, (
        "the entrypoint no longer skips generation when a config is mounted; a "
        "rendered INI may now be overwritten at startup"
    )


# ---------------------------------------------------------------------------
# Which pg_hba.conf line a PUBLISHED loopback port matches (Session 4 §3.2, D90)
#
# The single most dangerous assumption in Session 4. A published port arrives at
# the container through Docker NAT, so the source should be the bridge gateway
# and the connection should land on `host all all all scram-sha-256` rather than
# on `host all all 127.0.0.1/32 trust`. If it landed on trust, publishing a port
# would grant unauthenticated superuser access to every process on the host --
# and every credential test in this suite would still pass, because they all
# authenticate correctly.
#
# Measured here rather than reasoned about, and re-measured wherever this runs:
# it is a fact about the Docker daemon on the machine, not about the repository.
# ---------------------------------------------------------------------------


class PublishedCluster:
    """A throwaway cluster reachable through a published loopback port."""

    def __init__(self, name: str, port: int, image: str, good: Path, bad: Path) -> None:
        self.name = name
        self.port = port
        self.image = image
        self.good = good
        self.bad = bad

    def through_the_published_port(self, env_file: Path, statement: str):
        """Connect the way a developer would: host loopback, host network."""
        return subprocess.run(
            [
                "docker", "run", "--rm", "--network", "host",
                "--env-file", str(env_file), self.image,
                "psql", "-h", "127.0.0.1", "-p", str(self.port),
                "-U", "postgres", "-d", "postgres", "-w", "-X", "-qtA", "-c", statement,
            ],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip

    def through_the_containers_own_loopback(self, statement: str):
        """The control path: 127.0.0.1 as the server itself sees it."""
        return subprocess.run(
            [
                "docker", "exec", "-e", "PGPASSWORD=not-the-password", self.name,
                "psql", "-h", "127.0.0.1", "-p", "5432",
                "-U", "postgres", "-d", "postgres", "-w", "-X", "-qtA", "-c", statement,
            ],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip

    def logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.name],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return result.stdout + result.stderr

    def hba_line(self, number: int) -> str:
        result = subprocess.run(
            ["docker", "exec", self.name, "sh", "-c", f'sed -n "{number}p" "$PGDATA"/pg_hba.conf'],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()


@pytest.fixture(scope="module")
def published_cluster(postgres_image: str, tmp_path_factory: pytest.TempPathFactory):
    """Publish on an ephemeral loopback port, so no fixed port can collide.

    The password reaches both containers through `--env-file`. Passing it as
    `-e POSTGRES_PASSWORD=...` would put a secret in argv, which this repository
    forbids everywhere else and should not do in the test that exists to prove
    the boundary works.
    """
    name = f"apg-hba-probe-{secrets.token_hex(4)}"
    work = tmp_path_factory.mktemp("hba-probe")
    password = secrets.token_hex(24)

    server_env = work / "server.env"
    server_env.write_text(f"POSTGRES_PASSWORD={password}\n", encoding="utf-8")
    good = work / "good.env"
    good.write_text(f"PGPASSWORD={password}\n", encoding="utf-8")
    bad = work / "bad.env"
    bad.write_text("PGPASSWORD=not-the-password\n", encoding="utf-8")
    for path in (server_env, good, bad):
        path.chmod(0o600)

    started = subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            "--env-file", str(server_env),
            "-p", "127.0.0.1:0:5432",
            postgres_image, "-c", "log_connections=on",
        ],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr

    try:
        # Over TCP, and that is the whole fix. `pg_isready` connects on the
        # unix socket, and during initdb's bootstrap phase PostgreSQL runs with
        # `listen_addresses = ''` -- so the socket answers while a TCP
        # connection is refused, and every test using these fixtures connects
        # over TCP. Waiting on the socket reported ready and then handed out a
        # cluster that refused the *positive control*, which reads as a broken
        # instrument rather than as a race.
        #
        # `-h 127.0.0.1` explicitly: psql prefers the socket when given no host,
        # which would make this poll the same wrong thing more slowly.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                    "-tAc",
                    "SELECT 1",
                ],
                capture_output=True,
                check=False,
                timeout=60,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("the throwaway cluster never accepted a TCP connection on its own loopback")

        mapping = subprocess.run(
            ["docker", "port", name, "5432"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert mapping.returncode == 0, mapping.stderr
        published = int(mapping.stdout.strip().splitlines()[0].rsplit(":", 1)[-1])

        yield PublishedCluster(name, published, postgres_image, good, bad)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False, timeout=120)


@requires_docker
def test_the_probe_can_tell_a_trusted_path_from_an_authenticated_one(
    published_cluster: PublishedCluster,
) -> None:
    """The control, named so a broken probe fails under its own name.

    Without this, a run in which *both* paths rejected the wrong password would
    read as proof of the property below and would only mean the probe was
    broken. The image trusts its own loopback, so the same wrong password must
    succeed here.
    """
    result = published_cluster.through_the_containers_own_loopback("SELECT 'trusted'")
    assert result.returncode == 0, (
        "the container's own loopback rejected a wrong password, so this probe "
        f"cannot distinguish trust from scram: {result.stderr}"
    )
    assert "trusted" in result.stdout


@requires_docker
def test_a_published_loopback_port_arrives_from_a_non_loopback_address(
    published_cluster: PublishedCluster,
) -> None:
    result = published_cluster.through_the_published_port(
        published_cluster.good, "SELECT coalesce(inet_client_addr()::text, 'local')"
    )
    assert result.returncode == 0, result.stderr
    source = result.stdout.strip()
    assert source not in ("local", ""), "the connection did not traverse the published port"
    assert not source.startswith("127."), (
        f"the server saw {source}; a published port that presents as loopback "
        "would match the trust line"
    )


@requires_docker
def test_a_published_loopback_port_does_not_match_the_trust_line(
    published_cluster: PublishedCluster,
) -> None:
    """The measurement Session 4's publication decision rests on.

    Two independent assertions, because either alone can be satisfied by an
    accident: the wrong password is refused, *and* the server's own log names an
    HBA line whose address column is `all` rather than `127.0.0.1/32`.
    """
    refused = published_cluster.through_the_published_port(
        published_cluster.bad, "SELECT 'THE PUBLISHED PORT IS UNAUTHENTICATED'"
    )
    assert refused.returncode != 0, (
        "a wrong password opened a session through the published port: the port "
        "matched a trust rule and grants unauthenticated access to the host"
    )
    assert "password authentication failed" in refused.stderr, refused.stderr

    # Read once: two reads could straddle a connection and correlate a PID from
    # one snapshot against a source address that is only in the other.
    log = published_cluster.logs()
    received = dict(re.findall(r"\[(\d+)\] LOG:  connection received: host=(\S+)", log))
    authenticated = re.findall(
        r"\[(\d+)\] LOG:  connection authenticated: .*method=(\S+) \(\S+:(\d+)\)", log
    )
    matched = [
        (method, int(line))
        for pid, method, line in authenticated
        if not received.get(pid, "").startswith(("127.", "[local]", "::1"))
    ]
    assert matched, "no authenticated connection arrived from a non-loopback source"

    for method, line_number in matched:
        assert method == "scram-sha-256", f"a NAT'd connection authenticated by {method}"
        fields = published_cluster.hba_line(line_number).split()
        assert fields[:3] == ["host", "all", "all"], fields
        assert fields[3] == "all", (
            f"the published port matched {fields}; an address-scoped rule here "
            "means the source address is not what this test measured"
        )
        assert fields[4] == "scram-sha-256", fields


# ---------------------------------------------------------------------------
# And which line a CONTAINER-TO-CONTAINER connection matches (Session 5 Run 5)
#
# Session 4 measured the published-port case above. PostgREST does not use it:
# it reaches the cluster over the project's internal Docker network, which is a
# different source address arriving from a different bridge. Inheriting the
# earlier answer would be assuming two NAT paths behave alike, and the
# consequence of being wrong is unauthenticated superuser access from inside the
# project network -- available to anything that gets a foothold in any container
# on it, and invisible to every credential test in this suite, because they all
# authenticate correctly.
# ---------------------------------------------------------------------------


class PeerCluster:
    """A throwaway cluster with no published port, reached over its network."""

    def __init__(self, name: str, network: str, image: str, good: Path, bad: Path) -> None:
        self.name = name
        self.network = network
        self.image = image
        self.good = good
        self.bad = bad

    def from_a_peer_container(self, env_file: Path, statement: str):
        """Connect the way the API service does: by service name, over the network."""
        return subprocess.run(
            [
                "docker", "run", "--rm", "--network", self.network,
                "--env-file", str(env_file), self.image,
                "psql", "-h", "postgres", "-p", "5432",
                "-U", "postgres", "-d", "postgres", "-w", "-X", "-qtA", "-c", statement,
            ],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip

    def through_the_containers_own_loopback(self, statement: str):
        return subprocess.run(
            [
                "docker", "exec", "-e", "PGPASSWORD=not-the-password", self.name,
                "psql", "-h", "127.0.0.1", "-p", "5432",
                "-U", "postgres", "-d", "postgres", "-w", "-X", "-qtA", "-c", statement,
            ],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip

    def logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.name], capture_output=True, text=True, check=False, timeout=60
        )
        return result.stdout + result.stderr

    def hba_line(self, number: int) -> str:
        result = subprocess.run(
            ["docker", "exec", self.name, "sh", "-c", f'sed -n "{number}p" "$PGDATA"/pg_hba.conf'],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()


@pytest.fixture(scope="module")
def peer_cluster(postgres_image: str, tmp_path_factory: pytest.TempPathFactory):
    """No published port at all: the only route in is the project network.

    `--network-alias postgres` so the peer resolves the cluster by the name the
    Compose model uses, rather than by an address this test invented.
    """
    suffix = secrets.token_hex(4)
    name = f"apg-peer-probe-{suffix}"
    network = f"apg-peer-net-{suffix}"
    work = tmp_path_factory.mktemp("peer-probe")
    password = secrets.token_hex(24)

    server_env = work / "server.env"
    server_env.write_text(f"POSTGRES_PASSWORD={password}\n", encoding="utf-8")
    good = work / "good.env"
    good.write_text(f"PGPASSWORD={password}\n", encoding="utf-8")
    bad = work / "bad.env"
    bad.write_text("PGPASSWORD=not-the-password\n", encoding="utf-8")
    for path in (server_env, good, bad):
        path.chmod(0o600)

    created = subprocess.run(
        ["docker", "network", "create", network],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert created.returncode == 0, created.stderr

    started = subprocess.run(
        [
            "docker", "run", "-d", "--name", name,
            "--network", network, "--network-alias", "postgres",
            "--env-file", str(server_env),
            postgres_image, "-c", "log_connections=on",
        ],
        capture_output=True, text=True, check=False, timeout=300,
    )  # fmt: skip
    assert started.returncode == 0, started.stderr

    try:
        # Over TCP, and that is the whole fix. `pg_isready` connects on the
        # unix socket, and during initdb's bootstrap phase PostgreSQL runs with
        # `listen_addresses = ''` -- so the socket answers while a TCP
        # connection is refused, and every test using these fixtures connects
        # over TCP. Waiting on the socket reported ready and then handed out a
        # cluster that refused the *positive control*, which reads as a broken
        # instrument rather than as a race.
        #
        # `-h 127.0.0.1` explicitly: psql prefers the socket when given no host,
        # which would make this poll the same wrong thing more slowly.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                    "-tAc",
                    "SELECT 1",
                ],
                capture_output=True,
                check=False,
                timeout=60,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("the throwaway cluster never accepted a TCP connection on its own loopback")

        yield PeerCluster(name, network, postgres_image, good, bad)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False, timeout=120)
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, check=False, timeout=120
        )


@requires_docker
def test_the_peer_probe_can_tell_a_trusted_path_from_an_authenticated_one(
    peer_cluster: PeerCluster,
) -> None:
    """The control, again, and for the same reason.

    A run in which both paths rejected the wrong password would read as proof of
    the property below and would only mean the probe was broken.
    """
    result = peer_cluster.through_the_containers_own_loopback("SELECT 'trusted'")
    assert result.returncode == 0, (
        "the container's own loopback rejected a wrong password, so this probe "
        f"cannot distinguish trust from scram: {result.stderr}"
    )
    assert "trusted" in result.stdout


@requires_docker
def test_a_peer_container_arrives_from_the_project_network(peer_cluster: PeerCluster) -> None:
    result = peer_cluster.from_a_peer_container(
        peer_cluster.good, "SELECT coalesce(inet_client_addr()::text, 'local')"
    )
    assert result.returncode == 0, result.stderr
    source = result.stdout.strip()
    assert source not in ("local", ""), "the connection did not traverse the network"
    assert not source.startswith("127."), (
        f"the server saw {source}; a peer that presented as loopback would match "
        "the trust line and reach superuser without a password"
    )


@requires_docker
def test_a_peer_container_does_not_match_the_trust_line(peer_cluster: PeerCluster) -> None:
    """What Session 5 rests on: the API's own connection is authenticated.

    Same construction as the published-port measurement above -- the wrong
    password is refused, *and* the server's own log names an HBA line whose
    address column is `all`. Either alone can be satisfied by an accident.
    """
    refused = peer_cluster.from_a_peer_container(
        peer_cluster.bad, "SELECT 'THE PROJECT NETWORK IS UNAUTHENTICATED'"
    )
    assert refused.returncode != 0, (
        "a wrong password opened a session from a peer container: anything on the "
        "project network holds unauthenticated superuser access to the cluster"
    )
    assert "password authentication failed" in refused.stderr, refused.stderr

    log = peer_cluster.logs()
    received = dict(re.findall(r"\[(\d+)\] LOG:  connection received: host=(\S+)", log))
    authenticated = re.findall(
        r"\[(\d+)\] LOG:  connection authenticated: .*method=(\S+) \(\S+:(\d+)\)", log
    )
    matched = [
        (method, int(line))
        for pid, method, line in authenticated
        if not received.get(pid, "").startswith(("127.", "[local]", "::1"))
    ]
    assert matched, "no authenticated connection arrived from a peer container"

    for method, line_number in matched:
        assert method == "scram-sha-256", f"a peer container authenticated by {method}"
        fields = peer_cluster.hba_line(line_number).split()
        assert fields[:3] == ["host", "all", "all"], fields
        assert fields[3] == "all", (
            f"the peer connection matched {fields}; an address-scoped rule here "
            "means the source address is not what this test measured"
        )
        assert fields[4] == "scram-sha-256", fields


def test_the_model_puts_dbmate_flags_where_they_are_accepted() -> None:
    """Offline. The Compose command must obey what the measurements found."""
    import yaml

    model = yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    command = [str(item) for item in model["services"]["dbmate"]["command"]]
    subcommands = [
        item
        for item in command
        if not item.startswith("--") and item in {"up", "migrate", "status", "wait", "dump"}
    ]
    assert subcommands, f"no dbmate subcommand in {command}"
    first = command.index(subcommands[0])
    for flag in command[:first]:
        if flag.startswith("--"):
            assert flag in DBMATE_GLOBAL_FLAGS or flag == "--env", (
                f"{flag} precedes the subcommand but is not a global flag"
            )
    for flag in command[first + 1 :]:
        if flag.startswith("--"):
            allowed = DBMATE_SUBCOMMAND_FLAGS.get(subcommands[0], ())
            assert flag in allowed, f"{flag} follows {subcommands[0]}, which does not accept it"


# ---------------------------------------------------------------------------
# The locked PostgREST (Session 5 plan §3.2, D127)
#
# Everything here was measured against both v13.0.4 -- pinned since Session 1 --
# and v14.16, before the bump was made. The bump has exactly one reason and it
# is in this file rather than in the plan: on a distroless image with no shell
# and no HTTP client, `postgrest --ready` is the only probe that can run inside
# the container, and 13.0.4 does not have it.
# ---------------------------------------------------------------------------

#: What `postgrest --version` prints for the locked digest.
POSTGREST_VERSION = "14.16"

#: The complete key set the locked binary accepts, read from `--dump-config`.
#: Written down here because a key the parser drops is a boundary that is not
#: there, and nothing offline can tell the difference between a setting that is
#: enforced and a setting that is ignored.
POSTGREST_CONFIG_KEYS = frozenset(
    {
        "admin-server-host",
        "admin-server-port",
        "db-aggregates-enabled",
        "db-anon-role",
        "db-channel",
        "db-channel-enabled",
        "db-config",
        "db-extra-search-path",
        "db-hoisted-tx-settings",
        "db-max-rows",
        "db-plan-enabled",
        "db-pool",
        "db-pool-acquisition-timeout",
        "db-pool-automatic-recovery",
        "db-pool-max-idletime",
        "db-pool-max-lifetime",
        "db-pre-config",
        "db-pre-request",
        "db-prepared-statements",
        "db-root-spec",
        "db-schemas",
        "db-tx-end",
        "db-uri",
        "jwt-aud",
        "jwt-cache-max-entries",
        "jwt-role-claim-key",
        "jwt-secret",
        "jwt-secret-is-base64",
        "log-level",
        "log-query",
        "openapi-mode",
        "openapi-security-active",
        "openapi-server-proxy-uri",
        "server-cors-allowed-origins",
        "server-host",
        "server-port",
        "server-timing-enabled",
        "server-trace-header",
        "server-unix-socket",
        "server-unix-socket-mode",
    }
)

#: Set by the runbook's §11.3 baseline and asserted by its §16.2 gate. It does
#: not exist before 16.0. Named rather than merely omitted, so that a later
#: session reaching for it finds the measurement instead of the documentation.
POSTGREST_KEYS_THAT_DO_NOT_EXIST_YET = ("client-error-verbosity",)

#: Defaults that are dangerous rather than merely wrong, so the rendered
#: configuration has to set them explicitly and a test has to prove it did.
POSTGREST_DANGEROUS_DEFAULTS = {
    # `public` in the request search path is the whole of what ADR 0052 and
    # API-SCHEMA-001 are about, and it is what you get by not deciding.
    "db-extra-search-path": "public",
    # Database-sourced configuration overriding the reviewed file is the
    # default. `db-config = false` is what turns the file into the authority.
    "db-config": "true",
    # Not empty. Three settings are hoisted unless this is set.
    "db-hoisted-tx-settings": (
        "statement_timeout,plan_filter.statement_cost_limit,default_transaction_isolation"
    ),
}


@pytest.fixture(scope="module")
def postgrest_image() -> str:
    image = LOCK["POSTGREST_IMAGE"]
    subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", "-q", image],
        capture_output=True,
        check=False,
        timeout=600,
    )
    return image


def run_postgrest(*args: str, image: str) -> subprocess.CompletedProcess[str]:
    """Run the binary, naming it explicitly.

    The image declares no ``ENTRYPOINT``, so the shared ``run`` helper's
    arguments land in ``exec`` position and ``--version`` comes back as an
    executable that does not exist. Not a quirk worth hiding: it is the same
    reason the Compose service must name its command rather than inherit one.
    """
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--entrypoint",
            "postgrest",
            image,
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def dump_postgrest_config(directory: Path, image: str, extra: str = "") -> dict[str, str]:
    """``--dump-config`` output, parsed, for a minimal config plus ``extra``.

    It connects to the database before dumping, so it emits two PGRST000
    warnings against an unreachable host and dumps anyway. Those go to stderr
    and the dump goes to stdout, which is the only reason this is usable
    offline.

    It also prints ``db-uri`` **verbatim**, password included. Every caller here
    feeds it a deliberately worthless URI for that reason, and the Session 5
    entrypoint must never dump a config carrying a real one to anywhere but a
    protected tmpfs.
    """
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o755)
    (directory / "postgrest.conf").write_text(
        'db-uri = "postgresql://nobody@127.0.0.1:1/nothing"\n'
        'db-schemas = "api"\n'
        'db-anon-role = "anon"\n' + extra,
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "-v",
            f"{directory}:/cfg:ro",
            "--entrypoint",
            "postgrest",
            image,
            "--dump-config",
            "/cfg/postgrest.conf",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    settings: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(" = ")
        if separator:
            settings[key.strip()] = value.strip().strip('"')
    assert settings, result.stdout
    return settings


@pytest.fixture(scope="module")
def postgrest_dumped_config(postgrest_image: str, tmp_path_factory: pytest.TempPathFactory) -> dict:
    return dump_postgrest_config(tmp_path_factory.mktemp("postgrest-config"), postgrest_image)


@requires_docker
def test_postgrest_reports_the_measured_version(postgrest_image: str) -> None:
    result = run_postgrest("--version", image=postgrest_image)
    assert result.returncode == 0, result.stderr
    assert POSTGREST_VERSION in result.stdout, result.stdout


@requires_docker
def test_the_postgrest_image_has_no_shell(postgrest_image: str) -> None:
    """The fact that decided the healthcheck, and then the version.

    Distroless: no shell, no wget, no curl. A Compose healthcheck therefore
    cannot be ``CMD-SHELL`` and cannot run an HTTP client, which leaves the
    binary itself -- and on 13.0.4 the binary had no probe subcommand at all.

    Asserted rather than assumed because the alternative failure is silent in
    the worst way: a ``CMD-SHELL`` healthcheck on an image with no shell is
    reported by Docker as an unhealthy container, and the obvious repair is to
    weaken the check rather than to notice the image.
    """
    result = run("echo hi", image=postgrest_image, via_sh=True)
    assert result.returncode != 0, "the image has a shell; the healthcheck constraint is wrong"
    assert "executable file not found" in (result.stderr + result.stdout), result.stderr


@requires_docker
def test_postgrest_has_the_readiness_probe_that_forced_the_bump(postgrest_image: str) -> None:
    """`--ready` is the whole reason 13.0.4 was left behind (D127)."""
    result = run_postgrest("--help", image=postgrest_image)
    assert result.returncode == 0, result.stderr
    assert "--ready" in result.stdout, (
        "the locked PostgREST has no --ready, and on a distroless image there is "
        "then no way to probe it from inside its own container"
    )


@requires_docker
def test_the_config_key_set_is_the_measured_one(postgrest_dumped_config: dict) -> None:
    """Every key this session sets must be one the binary admits.

    ADR 0019 is why this is a test rather than a reading. A floor was once
    written to guarantee a Traefik key that exists in no version: the floor was
    real, the feature was not, and nothing offline could tell the difference.
    """
    assert set(postgrest_dumped_config) == POSTGREST_CONFIG_KEYS, {
        "unexpected": sorted(set(postgrest_dumped_config) - POSTGREST_CONFIG_KEYS),
        "missing": sorted(POSTGREST_CONFIG_KEYS - set(postgrest_dumped_config)),
    }


@requires_docker
@pytest.mark.parametrize("key", POSTGREST_KEYS_THAT_DO_NOT_EXIST_YET)
def test_a_key_the_runbook_requires_does_not_exist(postgrest_dumped_config: dict, key: str) -> None:
    """The runbook's own §11.3 sets it and its §16.2 asserts it (D144).

    It arrives in 16.0. Recorded as a test rather than as a note because the day
    it starts existing is the day this session's error-wrapper mitigation can be
    reconsidered, and a passing test is a worse messenger than a failing one.
    """
    assert key not in postgrest_dumped_config, (
        f"{key} now exists in the locked PostgREST. Session 5 works around its "
        "absence in the RPC error wrapper; revisit that with an ADR."
    )


@requires_docker
@pytest.mark.parametrize(("key", "value"), sorted(POSTGREST_DANGEROUS_DEFAULTS.items()))
def test_the_dangerous_defaults_are_what_they_were_measured_to_be(
    postgrest_dumped_config: dict, key: str, value: str
) -> None:
    """Three settings whose default is the thing this session must not have.

    ``db-extra-search-path`` defaults to ``public``; ``db-config`` defaults to
    letting the database override the reviewed file; ``db-hoisted-tx-settings``
    defaults to hoisting three settings rather than none.

    A rendered configuration that omitted any of them would be wrong in exactly
    the direction nobody checks, so the render sets all three explicitly and
    this records what "explicitly" is protecting against.
    """
    assert postgrest_dumped_config[key] == value, (
        f"{key} no longer defaults to {value!r}; the render's explicit setting "
        "was protecting against a default that has changed"
    )


# ---------------------------------------------------------------------------
# The admin surface, and the probe that reads it (Session 5, Run 3)
#
# Two measurements, and the runbook and this repository's own Run 1 note were
# each wrong about one of them.
# ---------------------------------------------------------------------------

#: What `server-host` must be for a container: the service has to answer its
#: peers on the project network, so it cannot bind loopback. S104 is exactly the
#: point of this constant -- the whole finding is that binding the request
#: surface widely also binds the admin surface widely.
POSTGREST_SERVICE_BIND = "0.0.0.0"  # noqa: S104


@requires_docker
def test_the_admin_server_binds_whatever_the_public_server_binds(
    postgrest_image: str, tmp_path: Path
) -> None:
    """The admin surface is loopback-only when it is told to be, and not before.

    Measured, with a control, because it is the kind of fact that gets written
    down from documentation: with `server-host = "0.0.0.0"` and only
    `admin-server-port` set, `admin-server-host` **mirrors the public bind** --
    and `/live` and `/ready` were reached from a peer container on the project
    network. Setting `admin-server-host = "127.0.0.1"` refuses that peer while
    `--ready` from inside the container still answers.

    That is why the rendered configuration sets it explicitly. A service whose
    public bind is `0.0.0.0` -- which every containerised one is -- publishes its
    admin surface to every container that can reach it, by doing nothing.
    """
    default = dump_postgrest_config(
        tmp_path / "default", postgrest_image, f'server-host = "{POSTGREST_SERVICE_BIND}"\n'
    )
    assert default["admin-server-host"] == POSTGREST_SERVICE_BIND, (
        "admin-server-host no longer follows server-host. If it now defaults to "
        "loopback the explicit setting is redundant -- confirm that before removing it"
    )

    explicit = dump_postgrest_config(
        tmp_path / "explicit",
        postgrest_image,
        f'server-host = "{POSTGREST_SERVICE_BIND}"\nadmin-server-host = "127.0.0.1"\n',
    )
    assert explicit["admin-server-host"] == "127.0.0.1"
    assert explicit["server-host"] == POSTGREST_SERVICE_BIND, (
        "setting admin-server-host moved the public bind too; the two are not separate"
    )


@requires_docker
def test_the_admin_server_is_off_until_a_port_is_named(postgrest_dumped_config: dict) -> None:
    """No port, no admin server -- which is also what makes `--ready` fail.

    An empty string rather than a number, so the absence is representable. A
    service that never sets the port has no admin surface at all, and a
    healthcheck asking one for readiness gets *"Admin server is not running"*
    from a process that is serving requests perfectly well.
    """
    assert postgrest_dumped_config["admin-server-port"] == ""


@requires_docker
def test_the_readiness_probe_needs_its_own_configuration(postgrest_image: str) -> None:
    """`postgrest --ready` is a CLIENT, and it reads its own configuration.

    Not the running process's. Measured against a healthy service answering 200
    on its request path:

    * `postgrest --ready` with no argument -> exit 1, *"Admin server is not
      running"*, because this process has no `admin-server-port`;
    * `postgrest --ready /path/to/postgrest.conf` -> exit 0;
    * `PGRST_ADMIN_SERVER_PORT` alone -> exit 1, *"the --ready flag cannot be
      used when server-host is..."*, because the default host is a wildcard and
      it will not probe one;
    * both `PGRST_ADMIN_SERVER_HOST` and `PGRST_ADMIN_SERVER_PORT` -> exit 0.

    So the obvious Compose healthcheck -- `CMD ["postgrest", "--ready"]`, which
    is how the runbook's §11.6 reads -- **fails on a perfectly healthy
    container**. This asserts the shape of the failure rather than the message,
    so the healthcheck cannot be written the obvious way and pass here.

    There is no database in this test and none is needed: the refusal happens
    before anything is probed.
    """
    bare = run_postgrest("--ready", image=postgrest_image)
    assert bare.returncode != 0, (
        "`postgrest --ready` now succeeds with no configuration. If it has learned to "
        "find the running process's config, the healthcheck can be simplified -- with "
        "a measurement, not with this test deleted"
    )
    assert "admin-server-port" in (bare.stdout + bare.stderr).lower().replace("_", "-")
