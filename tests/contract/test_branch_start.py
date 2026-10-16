"""A branch's image is resolved at every start (Session 41, D2504, D2513, D2514, ADR 0271).

Session 40's branch pinned the index id `runnable_image` resolved at creation
in `branch.env`; the boot's rebuild of the parent's image moved the tag to a new
index and orphaned that id (D2497), so `start --all` handed compose an id that
did not resolve, compose tried to PULL it, and the branch stayed `stopped` with
no reason anybody could read (D2504).

Since 1.19.0 `branch.json` records the parent image's TAG, its PLATFORM manifest
digest and the platform, and every start resolves the image afresh through
`restore_drill.image_for` -- the tag's current index iff its platform manifest
is the recorded digest -- and rewrites `branch.env` before `compose up`. The
fake daemon below is rig 41c's shape: an unchanged rebuild moves the index id
and keeps the platform digest, the old id stops resolving, and the INDEX's own
descriptor digest differs from the platform one, so a reader that compared the
wrong digest is caught here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, branch_record, restore_drill

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "slot3-prod"
DOMAIN = "slot3.agenticpostgresql.com"
TAG = f"apg-{KEY}-postgres:latest"
PLATFORM = "linux/amd64"
#: Rig 41c's three digests' shape: the platform manifest the branch was made
#: with, the index the first build made (orphaned), the index after an
#: unchanged rebuild, and the index's OWN descriptor digest.
MADE_WITH = "sha256:2794179a" + "0" * 56
OLD_INDEX = "sha256:d677c532" + "0" * 56
NEW_INDEX = "sha256:82700cbc" + "0" * 56
INDEX_DESCRIPTOR = "sha256:1dd3c0de" + "0" * 56
CHANGED = "sha256:7cbc07f1" + "0" * 56


def _runtime() -> Any:
    spec = importlib.util.spec_from_file_location(
        "apg_branch_runtime_start", REPO_ROOT / "bin" / "branch-runtime.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Daemon:
    """`docker` after a rebuild: `TAG` names `index`, whose `platform` manifest
    is `platform_digest`; the old index no longer resolves; compose `up` is
    recorded with the `branch.env` it was handed."""

    def __init__(self, *, platform_digest: str, compose_exit: int = 0, index: str = NEW_INDEX):
        self.platform_digest = platform_digest
        self.compose_exit = compose_exit
        self.index = index
        self.calls: list[tuple[str, ...]] = []
        self.env_at_up: list[str] = []

    def __call__(self, *arguments: str, timeout: float = 60) -> subprocess.CompletedProcess:
        self.calls.append(arguments)
        if arguments[:2] == ("image", "inspect"):
            target = arguments[-1]
            if target == OLD_INDEX:
                return subprocess.CompletedProcess(arguments, 1, "", "No such image")
            if "--platform" in arguments and target == self.index:
                descriptor = {"digest": self.platform_digest, "platform": {"os": "linux"}}
                return subprocess.CompletedProcess(arguments, 0, json.dumps(descriptor), "")
            if "{{json .Descriptor}}" in arguments and target == self.index:
                return subprocess.CompletedProcess(
                    arguments, 0, json.dumps({"digest": INDEX_DESCRIPTOR}), ""
                )
            if target == TAG:
                return subprocess.CompletedProcess(arguments, 0, f"{self.index}\n", "")
            return subprocess.CompletedProcess(arguments, 1, "", "No such image")
        if arguments[0] == "compose":
            env = Path(arguments[arguments.index("--env-file") + 1])
            self.env_at_up.append(env.read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(
                arguments, self.compose_exit, "", "" if not self.compose_exit else "boom: up failed"
            )
        return subprocess.CompletedProcess(arguments, 0, "", "")

    def composed(self) -> int:
        return sum(1 for call in self.calls if call[0] == "compose")


def _branch(root: Path, *, identity: bool = True, state: str = "ready") -> Path:
    path = branch_record.record_path(KEY, "dev", root=root)
    branch_record.write(
        path,
        branch_record.Record(
            project_key=KEY, branch="dev", state=state, operation="x", requested_point=None,
            reached_point=None, timeline=2, parent_commit=None,
            pool_host=f"dev.pool.{DOMAIN}", direct_host=f"dev.direct.{DOMAIN}",
            expires_at=None, expires_for=None, unreclaimable_mb=192,
            created_at="2026-10-16T08:00:00Z", updated_at="2026-10-16T08:00:00Z",
            **({"image_tag": TAG, "image_digest": MADE_WITH, "image_platform": PLATFORM}
               if identity else {}),
        ),
    )  # fmt: skip
    (path.parent / "branch.env").write_text(
        f"COMPOSE_PROJECT_NAME=apg-{KEY}_dev\nBRANCH_POSTGRES_IMAGE={OLD_INDEX}\n"
        "BRANCH_PGBOUNCER_IMAGE=sha256:" + "7" * 64 + "\n",
        encoding="utf-8",
    )
    (path.parent / "compose.override.yaml").write_text("services: {}\n", encoding="utf-8")
    return path


@pytest.fixture
def started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    runtime = _runtime()
    monkeypatch.setattr(runtime, "BRANCH_ROOT", tmp_path / "branches")
    monkeypatch.setattr(runtime, "require_root", lambda: None)
    monkeypatch.setattr(runtime, "attach", lambda names: None)
    monkeypatch.setattr(runtime, "await_door", lambda hosts: ("ready", None))
    return runtime


def _start(runtime: Any) -> int:
    return runtime.command_start(argparse.Namespace(all=True))


def _record(runtime: Any) -> branch_record.Record:
    found = branch_record.read(branch_record.record_path(KEY, "dev", root=runtime.BRANCH_ROOT))
    assert found is not None
    return found


def test_a_start_resolves_the_image_from_the_tag_and_digest(
    started: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The orphaned id is never handed to compose: `branch.env` names the tag's
    NEW index when `up` runs, because its platform manifest is the recorded one.

    Goes red if: the start reuses the env file as written (the orphan reaches
    compose), or `image_for` compares the index's own digest."""
    path = _branch(started.BRANCH_ROOT)
    daemon = Daemon(platform_digest=MADE_WITH)
    monkeypatch.setattr(started, "docker", daemon)
    assert _start(started) == started.EXIT_OK
    assert daemon.composed() == 1
    (env,) = daemon.env_at_up
    assert f"BRANCH_POSTGRES_IMAGE={NEW_INDEX}" in env.splitlines(), env
    assert OLD_INDEX not in env
    record = _record(started)
    assert (record.state, record.door, record.reason) == ("ready", "ready", None)
    assert (path.parent / "branch.env").stat().st_mode & 0o777 == 0o600


def test_changed_content_is_refused_with_a_reason(
    started: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rebuild with changed content moves the platform digest: the branch is
    not started from another image -- compose is never asked -- and its record
    says `stopped` with the reason, exit 6 (D2513; rig 41c's control)."""
    _branch(started.BRANCH_ROOT)
    daemon = Daemon(platform_digest=CHANGED)
    monkeypatch.setattr(started, "docker", daemon)
    assert _start(started) == started.EXIT_UNKNOWN
    assert daemon.composed() == 0
    record = _record(started)
    assert record.state == "stopped"
    assert "the parent's image changed since this branch was made" in (record.reason or "")
    assert "reset the branch" in (record.reason or "")


def test_the_reason_is_recorded(started: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """D2514: a start compose refuses records Docker's own line as the reason,
    and the next start that comes back clears it."""
    _branch(started.BRANCH_ROOT)
    monkeypatch.setattr(started, "docker", Daemon(platform_digest=MADE_WITH, compose_exit=1))
    assert _start(started) == started.EXIT_UNKNOWN
    failed = _record(started)
    assert failed.state == "stopped" and "boom: up failed" in (failed.reason or ""), failed
    monkeypatch.setattr(started, "docker", Daemon(platform_digest=MADE_WITH))
    assert _start(started) == started.EXIT_OK
    back = _record(started)
    assert (back.state, back.reason) == ("ready", None), back


def test_a_branch_made_before_1_19_0_is_refused_with_its_reason(
    started: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A version 1 record -- 1.18.0's, which pinned the id -- is still READ (a
    reader charges and lists it), and a start refuses it with the reason rather
    than guessing its image; compose is never asked."""
    path = _branch(started.BRANCH_ROOT, identity=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    for member in ("image_tag", "image_digest", "image_platform", "door", "reason"):
        data.pop(member)
    data["schema_version"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    read = branch_record.read(path)
    assert read is not None and read.state == "ready" and not read.has_image_identity
    daemon = Daemon(platform_digest=MADE_WITH)
    monkeypatch.setattr(started, "docker", daemon)
    assert _start(started) == started.EXIT_UNKNOWN
    assert daemon.composed() == 0
    record = _record(started)
    assert record.state == "stopped"
    assert record.reason == branch_record.MADE_BEFORE_IMAGE_IDENTITY


def test_image_for_reads_the_platform_manifest_not_the_index() -> None:
    """`image_for`'s three answers over the rig-shaped daemon: the new index when
    the platform manifest is the recorded one; refused when it changed; refused
    when the tag names nothing -- and never the index descriptor's digest."""
    assert restore_drill.image_for(TAG, MADE_WITH, PLATFORM, Daemon(platform_digest=MADE_WITH)) == (
        NEW_INDEX
    )
    with pytest.raises(restore_drill.DrillError, match="changed since this branch was made"):
        restore_drill.image_for(TAG, MADE_WITH, PLATFORM, Daemon(platform_digest=CHANGED))
    with pytest.raises(restore_drill.DrillError, match="names no image"):
        restore_drill.image_for(
            "apg-gone:latest", MADE_WITH, PLATFORM, Daemon(platform_digest=MADE_WITH)
        )
    # The index's own descriptor is never what is compared.
    with pytest.raises(restore_drill.DrillError, match="changed since this branch was made"):
        restore_drill.image_for(TAG, INDEX_DESCRIPTOR, PLATFORM, Daemon(platform_digest=MADE_WITH))
