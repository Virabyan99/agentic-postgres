"""What the locked database images actually are (Session 3 plan §3.2).

Three numbers the runbook tells us to assume, measured instead. This module is
the only place their values are written down, which is why it runs against the
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

Marked `database` rather than `contract`: these need a container runtime, and
the Session 1 gate's `-m "contract and not future"` selection must stay
runnable in a checkout. A runner without Docker reports that it could not look,
never a verdict (ADR 0018).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.database, pytest.mark.p0]

#: Measured against the locked digests. Changing any of these is changing a
#: fact about an image, which means the lock moved -- so it belongs in the same
#: commit as a `bin/lock-versions.sh --update`, not in a fix-up.
POSTGRES_UID = 999
POSTGRES_GID = 999
POSTGRES_PGDATA = "/var/lib/postgresql/18/docker"
POSTGRES_VOLUME_TARGET = "/var/lib/postgresql"
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
    for key in ("POSTGRES_IMAGE", "DBMATE_IMAGE"):
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
        if consumer["service"] == "postgres"
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
