"""Session 40's host proofs: the kept slot's branch on the machine (ADR 0271).

`BR-LIVE-002`'s five node ids, run by the sweep as root (claim
`branch_host_live`) with `slot3-prod`'s branch `dev` LIVE -- after the
lifecycle, after `s40-branches.py` restored and reset it, after the reboot and
`s40-branches.py --after-reboot`, and before `--delete-only`. None of them
changes anything: containers, networks and volumes through `docker inspect`,
the cluster through `psql` on the container's own socket, the repository
through the parent's `pgbackrest info`, the charge through `bin/doctor.sh
capacity` (D1114: the product's own command).

**The deleted branch these proofs read is `tmp`**, the one the reconciler
deleted by its expiry before the sweep: `dev` is deleted after it (the external
half reads that deletion live). The parent's deployed document is
`APG_LIVE_SLOT_OUTPUTS`, the branches' record `APG_BRANCH_RECORD_FILE` (copied
op-readable after `--after-reboot`). **None of these five proofs has ever
executed.**
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, branch_plan, branch_record, naming, slot

pytestmark = [
    pytest.mark.p0,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_LIVE_SLOT_OUTPUTS", "APG_BRANCH_RECORD_FILE", "APG_HOST_MANIFEST"
    ),
]

BRANCH = "dev"
EXPIRED = "tmp"
REPOSITORY_PATH = "/var/lib/pgbackrest"


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _inspect(kind: str, name: str) -> dict[str, Any] | None:
    done = (
        _run("docker", kind, "inspect", name)
        if kind != "container"
        else _run("docker", "inspect", name)
    )
    if done.returncode != 0:
        return None
    return json.loads(done.stdout)[0]


def _sql(container: str, database: str, sql: str) -> str:
    done = _run(
        "docker",
        "exec",
        container,
        "psql",
        "-X",
        "-qtA",
        "-U",
        "postgres",
        "-d",
        database,
        "-c",
        sql,
    )
    assert done.returncode == 0, f"{container}: {done.stderr.strip()}"
    return done.stdout.strip()


@pytest.fixture(scope="module")
def parent() -> dict[str, Any]:
    path = Path(os.environ["APG_LIVE_SLOT_OUTPUTS"])
    if not path.is_file():
        pytest.fail(f"APG_LIVE_SLOT_OUTPUTS points at {path}, which does not exist")
    document = json.loads(path.read_text(encoding="utf-8"))
    key = document["project"]["key"]
    assert slot.SLOT_KEY.match(key), f"APG_LIVE_SLOT_OUTPUTS names {key}, not a slot's key"
    return document


@pytest.fixture(scope="module")
def record(parent: dict[str, Any]) -> dict[str, Any]:
    """The branches' record as it stood at the sweep: `live`, the reboot read."""
    path = Path(os.environ["APG_BRANCH_RECORD_FILE"])
    if not path.is_file():
        pytest.fail(f"APG_BRANCH_RECORD_FILE points at {path}, which does not exist")
    document = json.loads(path.read_text(encoding="utf-8"))
    # Session 41 re-runs these against its own record (D2518), Session 42 too (D2623).
    sessions = (40, 41, 42, 43, 44, 45, 46)  # the record sessions this proof reads (D2714)
    assert document.get("session") in sessions and document.get("kind") == "branches", (
        document.get("session"), document.get("kind"),
    )  # fmt: skip
    assert document.get("project_key") == parent["project"]["key"], document.get("project_key")
    assert document.get("phase") == "live", (
        f"the sweep runs with dev live, not {document.get('phase')}"
    )
    return document


@pytest.fixture(scope="module")
def live(as_root: None, parent: dict[str, Any]) -> branch_record.Record:
    """The live branch's own record on this host, `ready`."""
    del as_root
    found = branch_record.read(branch_record.record_path(parent["project"]["key"], BRANCH))
    assert found is not None and found.state == "ready", found
    return found


def test_the_branch_is_bounded_and_unreachable_from_the_repository(
    as_root: None, parent: dict[str, Any], live: branch_record.Record
) -> None:
    """ADR 0271 items 2-4: the branch's three containers run, each bounded --
    memory, processes, CPU; its postgres joins only the branch's internal
    network, its two poolers that and the branch's edge network, none the
    parent's backup network or the parent's own; no container mounts a
    repository or a parent secret path; the branch's postgres archives nothing
    (`archive_mode` off, `archive_command` `/bin/false`)."""
    del as_root
    key = parent["project"]["key"]
    names = naming.branch_names(key, BRANCH)
    backup = naming.backup_network_name(key)
    expected = {
        names.postgres_container: {names.internal_network},
        names.pool_container: {names.internal_network, names.edge_network},
        names.direct_container: {names.internal_network, names.edge_network},
    }
    for container, networks in expected.items():
        found = _inspect("container", container)
        assert found is not None, f"{container} does not exist"
        assert found["State"]["Running"] is True, (container, found["State"])
        limits = found["HostConfig"]
        assert limits["Memory"] > 0 and limits["PidsLimit"] and limits["NanoCpus"] > 0, (
            container, limits["Memory"], limits["PidsLimit"], limits["NanoCpus"],
        )  # fmt: skip
        joined = set(found["NetworkSettings"]["Networks"])
        assert joined == networks and backup not in joined, (container, joined)
        for mount in found["Mounts"]:
            destination = mount.get("Destination", "")
            assert not destination.startswith(REPOSITORY_PATH), (container, mount)
            assert "/run/secrets" not in destination and "secret" not in mount.get("Source", ""), (
                container,
                mount,
            )
    database = parent["database"]["name"]
    assert _sql(names.postgres_container, database, "SHOW archive_mode") == "off"
    # D2505: with archiving off PostgreSQL SHOWs `(disabled)` for the command,
    # whatever was configured (measured on the trip). So the CONFIGURED command
    # is read where it is set -- the container's own argv -- and held to
    # `branch_plan.persistent_command()`'s two archive settings.
    assert _sql(names.postgres_container, database, "SHOW archive_command") == "(disabled)"
    command = list((_inspect("container", names.postgres_container) or {})["Config"]["Cmd"])
    configured = {command[i + 1] for i, word in enumerate(command[:-1]) if word == "-c"}
    archive = {s for s in branch_plan.persistent_command() if s.startswith("archive_")}
    assert archive == {"archive_mode=off", "archive_command=/bin/false"}, archive
    assert archive <= configured, (archive, command)


def test_the_branch_is_charged(
    as_root: None, parent: dict[str, Any], live: branch_record.Record
) -> None:
    """ADR 0271 item 9, D2431: the product's own capacity reading names the live
    branch on its committed line with `small`'s 192 MiB -- the charge every
    deploy's admission and the branch's own admission read."""
    del as_root
    assert live.unreclaimable_mb == 192, live
    doctor = str(REPO_ROOT / "bin" / "doctor.sh")
    done = _run(
        doctor, "capacity", "--host", os.environ["APG_HOST_MANIFEST"], "--json", timeout=300
    )
    assert done.returncode in (0, 6), done.stderr[-1000:]
    committed = [
        check for check in json.loads(done.stdout)["checks"] if check["name"] == "committed"
    ]
    assert len(committed) == 1, committed
    text = json.dumps(committed[0])
    assert f"{parent['project']['key']}_{BRANCH} (branch) 192" in text, text


def test_the_parent_was_untouched(
    as_root: None, parent: dict[str, Any], live: branch_record.Record, record: dict[str, Any]
) -> None:
    """ADR 0271: a branch's restores read the parent's repository and never
    write the parent. Its database still holds its own identity row and the
    instance its document names; it is on a timeline ONE below the branch's (a
    branch promotes from the parent's, the parent never moves); its volume is
    the one the document derives, older than the branch; and every WAL the
    repository holds is on the parent's timeline -- the branch archived nothing
    into it."""
    del as_root
    key = parent["project"]["key"]
    container, database = parent["database"]["container"], parent["database"]["name"]
    timeline = int(_sql(container, database, "SELECT timeline_id FROM pg_control_checkpoint()"))
    assert live.timeline == timeline + 1, (live.timeline, timeline)
    identity = _sql(container, database, "SELECT project_key FROM app_private.project_identity")
    assert identity == key, identity
    volume = _inspect("volume", naming.postgres_volume_name(key))
    assert volume is not None, f"{naming.postgres_volume_name(key)} does not exist"
    created = datetime.fromisoformat(volume["CreatedAt"].replace("Z", "+00:00"))
    assert created < datetime.fromisoformat(live.created_at.replace("Z", "+00:00")), (
        created,
        live.created_at,
    )
    stanza = parent["backup"]["stanza"]
    info = _run(
        "docker", "exec", container, "pgbackrest", f"--stanza={stanza}", "--output=json", "info",
        timeout=600,
    )  # fmt: skip
    assert info.returncode == 0, info.stderr[-1000:]
    prefix = f"{timeline:08X}"
    archives = json.loads(info.stdout)[0]["archive"]
    assert archives, "the repository lists no archive"
    for archive in archives:
        for bound in ("min", "max"):
            wal = archive.get(bound) or ""
            assert wal.startswith(prefix), (archive.get("id"), bound, wal, prefix)
    assert record["observations"]["rows_at_T1"]["main"] == [0, "1,2"], record["observations"]


def test_the_branch_came_back_after_the_reboot(
    as_root: None, parent: dict[str, Any], live: branch_record.Record, record: dict[str, Any]
) -> None:
    """D2439: a branch has no unit of its own -- the reconciler's start brings
    it back with `branch-runtime.sh start --all`. After Sheet B1 every one of
    its three containers was started AFTER this boot, its record reads
    `ready`, and the customer's pool name admitted the branch's app role
    (`s40-branches.py --after-reboot`, before the sweep)."""
    del as_root
    booted = time.time() - float(Path("/proc/uptime").read_text().split()[0])
    names = naming.branch_names(parent["project"]["key"], BRANCH)
    for container in (names.postgres_container, names.pool_container, names.direct_container):
        found = _inspect("container", container)
        assert found is not None and found["State"]["Running"], container
        started = datetime.fromisoformat(found["State"]["StartedAt"][:26].rstrip("Z") + "+00:00")
        assert started.timestamp() > booted, (container, found["State"]["StartedAt"], booted)
    after = record["observations"]["after_reboot"]
    assert (after["pool_exit"], after["state"]) == (0, "ready"), after
    assert after["user"] == record["doors"]["pooled"]["user"], after
    assert datetime.fromisoformat(after["at"]).timestamp() > booted, (after, booted)
    assert datetime.now(UTC).timestamp() > booted


def test_a_deleted_branch_left_nothing(
    as_root: None, parent: dict[str, Any], record: dict[str, Any]
) -> None:
    """ADR 0271, D2438: the branch the reconciler deleted by its expiry left no
    container of its compose project, no volume, no network and no directory
    -- deletion removes exactly what its names derive, and the record says it
    was the expiry's (`origin = expiry`) that removed it."""
    del as_root
    expired = record["observations"]["tmp_expired"]
    assert (expired["origin"], expired["status"]) == ("expiry", "succeeded"), expired
    key = parent["project"]["key"]
    names = naming.branch_names(key, EXPIRED)
    label = f"label=com.docker.compose.project={names.compose_project}"
    listed = _run("docker", "ps", "-a", "--filter", label, "--format", "{{.Names}}")
    assert listed.returncode == 0 and listed.stdout.strip() == "", listed.stdout
    assert _inspect("volume", names.volume) is None, names.volume
    for network in (names.edge_network, names.internal_network):
        assert _inspect("network", network) is None, network
    assert not branch_record.branch_directory(key, EXPIRED).exists()
