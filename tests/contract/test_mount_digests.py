"""The label that lets Compose see a change it structurally cannot see.

D591. `install_rendered` ends in `os.replace(staging, destination)` -- a new
directory with new inodes -- and `project-runtime up` runs `up -d --build
--wait` with no `--force-recreate`. Compose's config hash covers the service
*definition*, and a bind mount's source path is the identical string on every
deploy, so nothing looks changed and a running container keeps its open handle
on a **deleted inode**.

Measured on the host: the installed `pgbackrest.conf` was `-r--r--r--` dated
06:14 while the running container saw `-rw------- 0 root root` dated 05:36 --
link count 0, from a container created before two consecutive correct fixes,
neither of which could reach it. Three deploys went to that one defect.

**What is proved here is the digest; what is NOT proved here is Compose.** That
a changed label actually causes a recreate is Compose's behaviour and needs a
running daemon, so it belongs to the host gate. These tests prove the two
properties the label has to have for that behaviour to be worth anything: it
moves when the mounted bytes move, and it does *not* move when they do not.
The second is as important as the first -- a digest that changed every render
would recreate every container on every deploy, which is `--force-recreate`
wearing a different hat.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def _override(**services: list[str]) -> bytes:
    """A runtime override naming `services` and their volume entries."""
    document = {"services": {name: {"volumes": volumes} for name, volumes in services.items()}}
    return yaml.safe_dump(document).encode("utf-8")


def test_a_named_volume_is_not_a_bind_mount_and_contributes_nothing(tmp_path: Path) -> None:
    """Docker creates a named volume on demand; a deploy never replaces its content.

    The defect is specifically about a *host path* whose inode changed under a
    running container, so including named volumes would add churn with no
    corresponding failure to catch.
    """
    mounted = tmp_path / "conf"
    mounted.write_text("x", encoding="utf-8")

    payload = _override(
        postgres=[f"{mounted}:/etc/pgbackrest/pgbackrest.conf:ro"],
        pooler=["apg-alpha-dev-postgres:/var/lib/postgresql/data"],
    )
    by_service = runtime_override.mounted_paths_by_service(payload)

    assert set(by_service) == {"postgres"}, (
        f"expected only the bind-mounting service, got {sorted(by_service)}"
    )
    assert by_service["postgres"] == (str(mounted),)


def test_the_digest_moves_when_the_mounted_bytes_move(tmp_path: Path) -> None:
    """The property the whole mechanism exists for.

    This is D588's repair arriving under a container that would not have been
    recreated to see it: the file's path is identical, its mode is identical,
    only its content differs.
    """
    mounted = tmp_path / "pgbackrest.conf"
    mounted.write_text("[global]\nrepo1-retention-full=2\n", encoding="utf-8")
    before = runtime_override.mounted_digest([str(mounted)])

    mounted.write_text("[global]\nrepo1-retention-full=4\n", encoding="utf-8")
    after = runtime_override.mounted_digest([str(mounted)])

    assert before != after, (
        "the digest did not move when the mounted file's content changed, so a "
        "container would not be recreated to see it -- which is D591 exactly"
    )


def test_the_digest_does_not_move_when_nothing_changed(tmp_path: Path) -> None:
    """As important as the previous one, and easier to get wrong.

    A digest that included an mtime, an inode or the render time would move on
    every deploy, and every container would be recreated on every deploy. That
    is `--force-recreate` with extra steps, and it is the outcome this mechanism
    was chosen over.
    """
    mounted = tmp_path / "jwks.json"
    mounted.write_text('{"keys": []}', encoding="utf-8")

    first = runtime_override.mounted_digest([str(mounted)])

    # Rewrite the identical bytes: a new inode, same content.
    replacement = tmp_path / ".jwks.incoming"
    replacement.write_text('{"keys": []}', encoding="utf-8")
    replacement.replace(mounted)

    # **The mtime is moved DELIBERATELY, by a whole day.** Battery arm U2 --
    # a digest covering `st_mtime_ns` instead of the bytes -- SURVIVED the first
    # version of this test, which relied on the replace happening to produce a
    # different timestamp. It does not: Linux stamps files from a coarse clock
    # with millisecond-order granularity, so two files written microseconds apart
    # share an mtime and the mutation was invisible. A test that cannot see the
    # defect it names is not evidence, whatever colour it is.
    stamp = mounted.stat().st_mtime + 86_400
    os.utime(mounted, (stamp, stamp))

    assert runtime_override.mounted_digest([str(mounted)]) == first, (
        "the digest moved although the content did not. If it covers an mtime or "
        "an inode, every deploy recreates every container -- which is the outcome "
        "this mechanism was chosen over"
    )


def test_an_artefact_appearing_later_changes_the_digest(tmp_path: Path) -> None:
    """Absence is part of the digest, deliberately.

    At step 5 a deferred service's artefacts do not exist yet, so refusing to
    compute would turn a correct deploy into a failure. Recording the absence
    instead means the artefact arriving is itself a change, and the container is
    recreated then rather than never.
    """
    missing = tmp_path / "not-yet.json"
    absent = runtime_override.mounted_digest([str(missing)])

    missing.write_text("{}", encoding="utf-8")
    present = runtime_override.mounted_digest([str(missing)])
    assert absent != present, "an artefact appearing did not change the digest"

    # **An absent file and an EMPTY one must differ**, and that is the case the
    # marker exists for. Battery arm U4 -- replacing the `<absent>` marker with
    # `b""` -- survived the first version of this test, because the file it
    # created held `{}` and the two digests differed on the content anyway. The
    # mutation was uninformative and the test was incomplete; both are fixed by
    # asking the question the marker actually answers.
    missing.write_text("", encoding="utf-8")
    assert runtime_override.mounted_digest([str(missing)]) != absent, (
        "an absent artefact and an empty one digest the same, so a file that "
        "arrives empty -- a truncated render, a failed write -- would not "
        "recreate the container that mounts it"
    )


def test_a_directory_mount_digests_every_file_under_it(tmp_path: Path) -> None:
    """The migration set is mounted as a directory, not a file."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001.sql").write_text("SELECT 1;", encoding="utf-8")
    before = runtime_override.mounted_digest([str(migrations)])

    (migrations / "0002.sql").write_text("SELECT 2;", encoding="utf-8")
    assert runtime_override.mounted_digest([str(migrations)]) != before, (
        "a file added to a mounted directory did not change the digest"
    )

    (migrations / "0002.sql").write_text("SELECT 3;", encoding="utf-8")
    changed = runtime_override.mounted_digest([str(migrations)])
    (migrations / "0002.sql").write_text("SELECT 2;", encoding="utf-8")
    assert runtime_override.mounted_digest([str(migrations)]) != changed, (
        "a file edited inside a mounted directory did not change the digest"
    )


def test_the_override_labels_only_services_that_bind_mount(tmp_path: Path) -> None:
    mounted = tmp_path / "conf"
    mounted.write_text("x", encoding="utf-8")
    payload = _override(
        postgres=[f"{mounted}:/etc/pgbackrest/pgbackrest.conf:ro"],
        pooler=["apg-alpha-dev-postgres:/var/lib/postgresql/data"],
    )

    document = runtime_override.build_mount_override(payload)
    assert sorted(document["services"]) == ["postgres"]
    labels = document["services"]["postgres"]["labels"]
    assert list(labels) == [runtime_override.MOUNT_DIGEST_LABEL]
    assert len(labels[runtime_override.MOUNT_DIGEST_LABEL]) == 64


def test_the_rendered_override_carries_no_byte_of_what_it_digested(tmp_path: Path) -> None:
    """Some of what a service mounts is a credential.

    The output is one hex digest per service. This asserts the obvious thing
    directly, because the file is written next to two overrides that DO name
    paths into the secret tree, and the reason this one may be read more freely
    is that it contains nothing.
    """
    secret = tmp_path / "app_runtime_password"
    secret.write_text("s3cr3t-value-nobody-should-see", encoding="utf-8")
    payload = _override(pgbouncer=[f"{secret}:/run/secrets/app_runtime_password:ro"])

    rendered = runtime_override.render_mount_override(payload).decode("utf-8")

    assert "s3cr3t-value-nobody-should-see" not in rendered
    assert runtime_override.MOUNT_DIGEST_LABEL in rendered


def test_compose_loads_the_override_the_renderer_writes() -> None:
    """One filename, two files that must agree on it.

    `bin/compose.sh` decides which `--file` arguments Compose gets and
    `runtime_override` decides what the renderer writes. A rename that moved one
    and not the other would leave the label unloaded, and every symptom of D591
    would return with nothing failing -- so the join is asserted rather than
    left to review.

    That a loaded label actually causes a recreate is Compose's behaviour and
    needs a daemon; it belongs to the host gate, not here.
    """
    compose = (REPO_ROOT / "bin" / "compose.sh").read_text(encoding="utf-8")
    assert runtime_override.MOUNT_OVERRIDE_FILENAME in compose, (
        f"bin/compose.sh does not name {runtime_override.MOUNT_OVERRIDE_FILENAME}, so the "
        "override is written and never loaded"
    )

    renderer = (REPO_ROOT / "bin" / "render-mount-digests.py").read_text(encoding="utf-8")
    assert "MOUNT_OVERRIDE_FILENAME" in renderer, (
        "the renderer spells the filename itself instead of reading the constant"
    )

    runtime = (REPO_ROOT / "bin" / "project-runtime.sh").read_text(encoding="utf-8")
    assert "render-mount-digests.py" in runtime, (
        "nothing writes the override before `up`, so it describes a previous start"
    )
