"""The record that decides what systemd runs as root, and who writes it.

`/etc/agentic-postgres/edge-state.json` had three readers and no writer. Both
root launchers open with a check for it and exit 3 without it, so
`agentic-postgres-docker-firewall.service` was enabled on a fully provisioned
host and had never executed once — the DOCKER-USER policy was present only
because `--apply` ran the reconciler out of the checkout by hand. A reboot would
have recreated the chain empty, and the edge unit `Requires=` the firewall unit,
so ingress would have failed with it.

Nothing in the suite noticed, because every test asked whether the file's
*consumers* were correct. None asked whether the file could exist.

The last test here is the general form of that question: no launcher may require
a state file that nothing in the repository writes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, edge_state
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

COMMIT = "a" * 40
DIGEST = "b" * 64


@pytest.fixture
def document() -> dict:
    return edge_state.build_state(installed_release_commit=COMMIT, host_manifest_sha256=DIGEST)


def test_a_built_record_validates(document: dict) -> None:
    assert edge_state.validate_state(document) == document
    assert document["schema_version"] == edge_state.SCHEMA_VERSION


def test_round_trip_through_disk(tmp_path: Path, document: dict) -> None:
    path = tmp_path / "edge-state.json"
    edge_state.write_state(document, path)
    assert edge_state.load_state(path) == document


def test_the_file_is_not_writable_by_anyone_but_root(tmp_path: Path, document: dict) -> None:
    """Writing this file chooses what root executes on the next boot."""
    path = edge_state.write_state(document, tmp_path / "edge-state.json")
    assert path.stat().st_mode & 0o022 == 0, oct(path.stat().st_mode)


@pytest.mark.parametrize(
    "commit",
    [
        "z" * 40,  # not hexadecimal
        "a" * 39,  # too short
        "a" * 41,  # too long
        "../../../etc/passwd",
        "A" * 40,  # uppercase: a different path on a case-sensitive filesystem
        "",
    ],
)
def test_a_commit_that_is_not_a_commit_is_refused(commit: str) -> None:
    """This value becomes a path component under /opt. It is never trusted."""
    with pytest.raises(Exception, match=r".") as raised:
        edge_state.build_state(installed_release_commit=commit, host_manifest_sha256=DIGEST)
    assert raised.type.__name__ in {"ReleaseError", "ManifestError"}


def test_an_unknown_field_is_refused(tmp_path: Path, document: dict) -> None:
    document["installed_release_path"] = "/opt/somewhere/else"
    with pytest.raises(ManifestError):
        edge_state.validate_state(document)


def test_a_truncated_file_is_refused_rather_than_half_read(tmp_path: Path, document: dict) -> None:
    path = tmp_path / "edge-state.json"
    path.write_text(json.dumps(document)[:40], encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        edge_state.load_state(path)


def test_a_symlink_is_refused_on_read_and_on_write(tmp_path: Path, document: dict) -> None:
    """The launchers refuse a symlink here; so does the writer.

    A symlink at this path redirects the write that decides what root executes.
    """
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "edge-state.json"
    link.symlink_to(real)

    with pytest.raises(ManifestError, match="symlink"):
        edge_state.load_state(link)
    with pytest.raises(ManifestError, match="symlink"):
        edge_state.write_state(document, link)


# ---------------------------------------------------------------------------
# The question nobody asked
# ---------------------------------------------------------------------------


def test_provision_host_installs_a_release_before_enabling_the_units(code_only) -> None:
    """Enabling a unit whose launcher cannot resolve a release trains an
    operator to ignore a failing service."""
    source = (REPO_ROOT / "bin" / "provision-host.sh").read_text(encoding="utf-8")
    body = code_only(source.split("apply_baseline()", 1)[1])
    assert "install_release" in body, "nothing installs a release during --apply"
    assert body.index("install_release") < body.index("install_units")


def test_every_state_file_a_launcher_requires_has_a_writer() -> None:
    """The general form of the defect.

    A launcher that exits 3 without a file nothing creates is a unit that can
    never start, and `systemctl enable` reports success either way.
    """
    # A file that *writes* something, not one that merely names it. The absent
    # writer was easy to miss precisely because `edge-state.json` appeared all
    # over the tree — in launchers, in comments, in an error message telling the
    # operator to run a command that did not create it.
    write_primitives = (
        "os.replace",
        "write_text",
        "write_bytes",
        "write_state",
        "install -m",
        "tee ",
        '> "',
    )

    sources = [
        (path, path.read_text(encoding="utf-8"))
        for directory in ("bin", "src")
        for path in sorted((REPO_ROOT / directory).rglob("*"))
        if path.is_file() and path.suffix in {".sh", ".py"}
    ]

    required: set[str] = set()
    for launcher in sorted((REPO_ROOT / "libexec").iterdir()):
        if not launcher.is_file():
            continue
        text = launcher.read_text(encoding="utf-8")
        for match in re.finditer(r'^readonly \w+="(/(?:etc|var)/[^"]+\.json)"', text, re.M):
            required.add(match.group(1))

    assert required, "no launcher declares a state file; this scan is measuring nothing"

    orphans = []
    for path in sorted(required):
        basename = path.rsplit("/", 1)[-1]
        writers = [
            source
            for source, text in sources
            if basename in text and any(token in text for token in write_primitives)
        ]
        if not writers:
            orphans.append(path)

    assert not orphans, (
        f"launchers require state files nothing in bin/ or src/ writes: {orphans}. "
        "The unit exits 3 on every boot and `systemctl enable` reports success regardless."
    )
