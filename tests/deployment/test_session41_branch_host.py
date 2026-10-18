"""Session 41's host proofs: the kept slot's branch on the machine, re-trialed (ADR 0271, D2504).

`BR-LIVE-004`'s six node ids, run by the sweep as root (claim
`branch_host_retrial_live`) with `slot3-prod`'s branch `dev` LIVE -- after
`s41-branches.py` restored and reset it, after the reboot and `s41-branches.py
--after-reboot`, before `--delete-only`. Session 40's five (`BR-LIVE-002`) re-run
against the same record; these add what Session 41 repaired: **the branch came
back after the reboot BY ITSELF** -- nothing reset it after the boot -- running
the image its record's tag and content digest resolve to now (D2504, D2513),
and **the diagnosis account sees it** (`apg-diag containers`, D2514). None of
them changes anything. The parent's deployed document is
`APG_LIVE_SLOT_OUTPUTS`, the branches' record `APG_BRANCH_RECORD_FILE`. **None of
these proofs has ever executed.**
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, branch_plan, branch_record, naming, restore_drill, slot

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
#: The diagnosis account's installed copy (Sheet PV re-installs it, D2542).
APG_DIAG = "/usr/local/bin/apg-diag"


def _run(*command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command), stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=timeout, check=False,
    )  # fmt: skip


def _docker(*arguments: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return _run("docker", *arguments, timeout=timeout)


def _inspect(kind: str, name: str) -> dict[str, Any] | None:
    done = _docker(kind, "inspect", name) if kind != "container" else _docker("inspect", name)
    if done.returncode != 0:
        return None
    return json.loads(done.stdout)[0]


def _sql(container: str, database: str, sql: str) -> str:
    done = _docker("exec", container, "psql", "-X", "-qtA", "-U", "postgres", "-d", database,
                   "-c", sql)  # fmt: skip
    assert done.returncode == 0, f"{container}: {done.stderr.strip()}"
    return done.stdout.strip()


def _booted() -> float:
    return time.time() - float(Path("/proc/uptime").read_text().split()[0])


def _at(text: str) -> float:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


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
    """Session 41's branches' record as it stood at the sweep: `live`, the
    reboot read."""
    path = Path(os.environ["APG_BRANCH_RECORD_FILE"])
    if not path.is_file():
        pytest.fail(f"APG_BRANCH_RECORD_FILE points at {path}, which does not exist")
    document = json.loads(path.read_text(encoding="utf-8"))
    # Session 42 re-runs these against its own record (D2623).
    assert document.get("session") in (41, 42) and document.get("kind") == "branches", (
        document.get("session"), document.get("kind"),
    )  # fmt: skip
    assert document.get("project_key") == parent["project"]["key"], document.get("project_key")
    assert document.get("phase") == "live", (
        f"the sweep runs with dev live, not {document.get('phase')}"
    )
    return document


@pytest.fixture(scope="module")
def live(as_root: None, parent: dict[str, Any]) -> branch_record.Record:
    """The live branch's own record on this host: `ready`, its door open, made
    with its image's identity (schema 2, D2513)."""
    del as_root
    found = branch_record.read(branch_record.record_path(parent["project"]["key"], BRANCH))
    assert found is not None and found.state == "ready", found
    assert found.door == "ready" and found.has_image_identity, found
    return found


def test_the_branch_is_bounded_and_configured_not_to_archive(
    as_root: None, parent: dict[str, Any], live: branch_record.Record
) -> None:
    """ADR 0271 items 2-4: the branch's three containers run, each bounded --
    memory, processes, CPU; its postgres joins only the branch's internal
    network, its two poolers that and the branch's edge network, none the
    parent's backup network; no container mounts a repository or a parent
    secret path; archiving is off and the CONFIGURED command is `/bin/false`,
    read from the container's own argv (D2505: SHOW reads `(disabled)`)."""
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
                container, mount,
            )  # fmt: skip
    database = parent["database"]["name"]
    assert _sql(names.postgres_container, database, "SHOW archive_mode") == "off"
    assert _sql(names.postgres_container, database, "SHOW archive_command") == "(disabled)"
    command = list((_inspect("container", names.postgres_container) or {})["Config"]["Cmd"])
    configured = {command[i + 1] for i, word in enumerate(command[:-1]) if word == "-c"}
    archive = {s for s in branch_plan.persistent_command() if s.startswith("archive_")}
    assert archive == {"archive_mode=off", "archive_command=/bin/false"}, archive
    assert archive <= configured, (archive, command)


def test_the_branch_is_charged(
    as_root: None, parent: dict[str, Any], live: branch_record.Record
) -> None:
    """ADR 0271 item 9: the product's own capacity reading names the live branch
    on its committed line with `small`'s 192 MiB."""
    del as_root
    assert live.unreclaimable_mb == 192, live
    doctor = str(REPO_ROOT / "bin" / "doctor.sh")
    done = _run(
        doctor, "capacity", "--host", os.environ["APG_HOST_MANIFEST"], "--json", timeout=300
    )
    assert done.returncode in (0, 6), done.stderr[-1000:]
    committed = [c for c in json.loads(done.stdout)["checks"] if c["name"] == "committed"]
    assert len(committed) == 1, committed
    text = json.dumps(committed[0])
    assert f"{parent['project']['key']}_{BRANCH} (branch) 192" in text, text


def test_the_parent_was_untouched(
    as_root: None, parent: dict[str, Any], live: branch_record.Record, record: dict[str, Any]
) -> None:
    """ADR 0271: a branch's restores read the parent's repository and never
    write the parent: its identity row, its timeline one below the branch's,
    its volume older than the branch, and every WAL in the repository on the
    parent's timeline."""
    del as_root
    key = parent["project"]["key"]
    container, database = parent["database"]["container"], parent["database"]["name"]
    timeline = int(_sql(container, database, "SELECT timeline_id FROM pg_control_checkpoint()"))
    assert live.timeline == timeline + 1, (live.timeline, timeline)
    identity = _sql(container, database, "SELECT project_key FROM app_private.project_identity")
    assert identity == key, identity
    volume = _inspect("volume", naming.postgres_volume_name(key))
    assert volume is not None, f"{naming.postgres_volume_name(key)} does not exist"
    assert _at(volume["CreatedAt"]) < _at(live.created_at), (volume["CreatedAt"], live.created_at)
    stanza = parent["backup"]["stanza"]
    info = _docker("exec", container, "pgbackrest", f"--stanza={stanza}", "--output=json", "info",
                   timeout=600)  # fmt: skip
    assert info.returncode == 0, info.stderr[-1000:]
    prefix = f"{timeline:08X}"
    archives = json.loads(info.stdout)[0]["archive"]
    assert archives, "the repository lists no archive"
    for archive in archives:
        for bound in ("min", "max"):
            wal = archive.get(bound) or ""
            assert wal.startswith(prefix), (archive.get("id"), bound, wal, prefix)
    assert record["observations"]["rows_at_T1"]["main"] == [0, "1,2"], record["observations"]


def test_the_branch_came_back_by_itself_after_the_reboot(
    as_root: None, parent: dict[str, Any], live: branch_record.Record, record: dict[str, Any]
) -> None:
    """D2504 repaired: after Sheet B1 every one of the branch's three containers
    was started AFTER this boot by the reconciler's `start --all` -- NOTHING
    reset it: no operation of the record finished after the boot -- its record
    reads `ready` with its door open, its postgres runs the image the record's
    tag and content digest resolve to NOW (never an id a rebuild orphaned), and
    the customer's pool name admitted the branch's app role before the sweep."""
    del as_root
    booted = _booted()
    names = naming.branch_names(parent["project"]["key"], BRANCH)
    for container in (names.postgres_container, names.pool_container, names.direct_container):
        found = _inspect("container", container)
        assert found is not None and found["State"]["Running"], container
        assert _at(found["State"]["StartedAt"][:26].rstrip("Z") + "+00:00") > booted, (
            container, found["State"]["StartedAt"], booted,
        )  # fmt: skip
    finished = [
        o for o in record["operations"] if o.get("finished_at") and _at(o["finished_at"]) > booted
    ]
    assert not finished, (
        f"an operation finished after the boot -- dev was not back by itself: {finished}"
    )
    assert live.image_tag and live.image_digest and live.image_platform, live
    # The tag still resolves to the recorded content (DrillError otherwise) ...
    restore_drill.image_for(live.image_tag, live.image_digest, live.image_platform, _docker)
    # ... and the running postgres IS that content: compared by its platform
    # manifest's digest, not its index id, which an unchanged rebuild moves (D2497).
    running = (_inspect("container", names.postgres_container) or {})["Image"]
    descriptor = _docker("image", "inspect", "--platform", live.image_platform,
                         "-f", "{{json .Descriptor}}", running)  # fmt: skip
    assert descriptor.returncode == 0, descriptor.stderr[-500:]
    assert json.loads(descriptor.stdout).get("digest") == live.image_digest, (
        running, descriptor.stdout, live.image_digest,
    )  # fmt: skip
    after = record["observations"]["after_reboot"]
    assert (after["pool_exit"], after["state"], after["door"]) == (0, "ready", "ready"), after
    assert after["user"] == record["doors"]["pooled"]["user"], after
    assert _at(after["at"]) > booted, (after, booted)


def test_the_diagnosis_account_sees_the_branch(
    as_root: None, parent: dict[str, Any], live: branch_record.Record
) -> None:
    """D2514: `apg-diag containers` -- the read-only diagnosis account's own
    command, the installed copy -- lists the branch under its own section with
    its three containers Up; before Session 41 a branch was invisible to it."""
    del as_root, live
    key = parent["project"]["key"]
    done = _run(APG_DIAG, "containers", timeout=180)
    assert done.returncode == 0, done.stderr[-1000:]
    assert f"-- {key}_{BRANCH} (branch)" in done.stdout, done.stdout[-2000:]
    names = naming.branch_names(key, BRANCH)
    up = [line for line in done.stdout.splitlines()
          for container in (names.postgres_container, names.pool_container, names.direct_container)
          if re.match(rf"^{re.escape(container)}\s+Up ", line)]  # fmt: skip
    assert len(up) == 3, done.stdout[-2000:]


def test_a_deleted_branch_left_nothing(
    as_root: None, parent: dict[str, Any], record: dict[str, Any]
) -> None:
    """ADR 0271, D2438: the branch the reconciler deleted by its expiry left no
    container of its compose project, no volume, no network and no directory."""
    del as_root
    expired = record["observations"]["tmp_expired"]
    assert (expired["origin"], expired["status"]) == ("expiry", "succeeded"), expired
    key = parent["project"]["key"]
    names = naming.branch_names(key, EXPIRED)
    label = f"label=com.docker.compose.project={names.compose_project}"
    listed = _docker("ps", "-a", "--filter", label, "--format", "{{.Names}}")
    assert listed.returncode == 0 and listed.stdout.strip() == "", listed.stdout
    assert _inspect("volume", names.volume) is None, names.volume
    for network in (names.edge_network, names.internal_network):
        assert _inspect("network", network) is None, network
    assert not branch_record.branch_directory(key, EXPIRED).exists()
