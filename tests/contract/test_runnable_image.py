"""A drill and a branch run the database container's OWN image, by an id that resolves (D2497).

Sheet V1b at `94d2354` (2026-10-15): all three beta drills failed `docker: No
such image: sha256:797d...` in 67 s. On the containerd image store every build
of `apg-<key>-postgres` moves the tag to a new index id -- the attestation
manifest differs each time -- and the index a running container was created from
stops resolving, while the platform image inside is byte-identical: rig 40f
measured the container's `ImageManifestDescriptor` digest equal to the rebuilt
tag's `linux/amd64` manifest, `docker run <old index id>` refused, and a pulled
image's id (the control) stayed resolvable. A deploy that changes nothing in the
database does not recreate it, so after any new commit's deploy every drill and
every BRANCH (`branch_plan` reads the parent's `inspect["Image"]` the same way)
failed. Yesterday's V1 drills passed only because the sweep's restart proofs had
recreated beta's container first.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, restore_drill

pytestmark = [pytest.mark.contract, pytest.mark.p0]

OWN = "sha256:" + "7" * 64
INDEX = "sha256:" + "0" * 64
PLATFORM = "sha256:" + "e" * 64
OTHER = "sha256:" + "f" * 64
TAG = "apg-beta-dev-postgres"


def _inspect(**overrides: Any) -> dict[str, Any]:
    inspect: dict[str, Any] = {
        "Image": OWN,
        "Config": {"Image": TAG},
        "ImageManifestDescriptor": {
            "digest": PLATFORM,
            "platform": {"os": "linux", "architecture": "amd64"},
        },
    }
    inspect.update(overrides)
    return inspect


class FakeDocker:
    """`docker image inspect` answers, by argv; anything else is a test error."""

    def __init__(self, *, own_resolves: bool, tag_index: str | None, platform: str | None):
        self.own_resolves = own_resolves
        self.tag_index = tag_index
        self.platform = platform
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *argv: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        assert argv[:2] == ("image", "inspect"), argv
        subject = argv[-1]
        if "--platform" in argv:
            assert argv[argv.index("--platform") + 1] == "linux/amd64"
            if subject == self.tag_index and self.platform is not None:
                return self._done(json.dumps({"digest": self.platform}))
            return self._done("", 1)
        if subject == OWN:
            return self._done(OWN) if self.own_resolves else self._done("", 1)
        if subject == TAG and self.tag_index:
            return self._done(self.tag_index + "\n")
        return self._done("", 1)

    @staticmethod
    def _done(stdout: str, code: int = 0) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], code, stdout, "")


def test_the_containers_own_id_when_it_resolves() -> None:
    docker = FakeDocker(own_resolves=True, tag_index=INDEX, platform=OTHER)
    assert restore_drill.runnable_image(_inspect(), docker) == OWN
    assert len(docker.calls) == 1, "a resolving id is used without reading the tag"


def test_an_orphaned_id_runs_the_tag_holding_the_same_platform_image() -> None:
    docker = FakeDocker(own_resolves=False, tag_index=INDEX, platform=PLATFORM)
    assert restore_drill.runnable_image(_inspect(), docker) == INDEX


def test_an_orphaned_id_refuses_a_tag_that_names_other_content() -> None:
    docker = FakeDocker(own_resolves=False, tag_index=INDEX, platform=OTHER)
    with pytest.raises(restore_drill.DrillError, match="no longer what"):
        restore_drill.runnable_image(_inspect(), docker)


def test_an_unreadable_platform_manifest_is_said_not_guessed() -> None:
    docker = FakeDocker(own_resolves=False, tag_index=INDEX, platform=None)
    with pytest.raises(restore_drill.DrillError, match="could not be determined"):
        restore_drill.runnable_image(_inspect(), docker)


def test_no_descriptor_or_no_tag_refuses() -> None:
    docker = FakeDocker(own_resolves=False, tag_index=INDEX, platform=PLATFORM)
    with pytest.raises(restore_drill.DrillError, match="no platform manifest"):
        restore_drill.runnable_image(_inspect(ImageManifestDescriptor=None), docker)
    with pytest.raises(restore_drill.DrillError, match="no platform manifest"):
        restore_drill.runnable_image(_inspect(Config={}), docker)
    absent = FakeDocker(own_resolves=False, tag_index=None, platform=PLATFORM)
    with pytest.raises(restore_drill.DrillError, match="names no image"):
        restore_drill.runnable_image(_inspect(), absent)


def test_the_drill_resolves_the_image_before_it_plans() -> None:
    text = (Path(REPO_ROOT) / "bin" / "restore-test.py").read_text(encoding="utf-8")
    resolve = text.find("restore_drill.runnable_image(inspect, docker)")
    planned = text.find("restore_drill.build_plan(")
    assert resolve != -1, "bin/restore-test.py runs the container's creation id unresolved (D2497)"
    assert planned != -1 and resolve < planned, "bin/restore-test.py plans before it resolves"


def test_every_branch_plan_is_built_from_a_resolved_parent() -> None:
    text = (Path(REPO_ROOT) / "bin" / "branch-runtime.py").read_text(encoding="utf-8")
    assert "restore_drill.runnable_image(inspect, docker)" in text
    plans = text.count("plan = build_plan(document, inspect,")
    resolved = text.count("inspect = runnable(")
    assert plans == 2 and resolved == plans, (
        f"{plans} branch plan(s), {resolved} built from a resolved parent inspect (D2497)"
    )
