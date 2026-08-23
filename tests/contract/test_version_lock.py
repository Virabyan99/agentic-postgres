"""Immutable image and version lock (runbook §6).

The failure-mode tests build a miniature repository in ``tmp_path`` — the
script resolves its own root from ``BASH_SOURCE``, so a copy of it operates on
the copied files — and then break one thing at a time. Asserting only that
``--check`` passes on the real lock would prove nothing about whether it can
detect anything.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

LOCK = REPO_ROOT / "versions.env"
CANDIDATES = REPO_ROOT / "versions.in.yaml"
SCRIPT = REPO_ROOT / "bin" / "lock-versions.sh"

IMAGE_REFERENCE = re.compile(
    r"^(?P<repo>[a-z0-9.\-]+(?::\d+)?/[a-z0-9._/\-]+)"
    r":(?P<tag>[A-Za-z0-9._\-]+)"
    r"@sha256:(?P<digest>[0-9a-f]{64})$"
)
FLOATING_TAGS = {"latest", "main", "master", "edge", "stable", "nightly", "dev"}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        assert key not in values, f"duplicate variable {key}"
        values[key] = value
    return values


@pytest.fixture(scope="module")
def lock() -> dict[str, str]:
    return parse_env(LOCK)


@pytest.fixture(scope="module")
def candidates() -> dict:
    return yaml.safe_load(CANDIDATES.read_text(encoding="utf-8"))


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A minimal repository the real script can operate on."""
    (tmp_path / "bin").mkdir()
    shutil.copy(SCRIPT, tmp_path / "bin" / "lock-versions.sh")
    (tmp_path / "bin" / "lock-versions.sh").chmod(0o755)
    shutil.copy(CANDIDATES, tmp_path / "versions.in.yaml")
    shutil.copy(LOCK, tmp_path / "versions.env")
    shutil.copy(REPO_ROOT / ".python-version", tmp_path / ".python-version")
    return tmp_path


def run_check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "bin" / "lock-versions.sh"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Format of the committed lock
# ---------------------------------------------------------------------------


def test_every_image_is_pinned_to_a_digest(lock: dict[str, str], candidates: dict) -> None:
    for name in candidates["images"]:
        reference = lock[name]
        assert IMAGE_REFERENCE.match(reference), f"{name} is not digest-pinned: {reference}"


def test_no_floating_tag_remains(lock: dict[str, str], candidates: dict) -> None:
    """Runbook §6.4 and the source specification's release gate."""
    for name in candidates["images"]:
        match = IMAGE_REFERENCE.match(lock[name])
        assert match is not None
        assert match.group("tag").lower() not in FLOATING_TAGS, name


def test_digests_are_lowercase_hex_of_the_right_length(
    lock: dict[str, str], candidates: dict
) -> None:
    for name in candidates["images"]:
        digest = lock[name].split("@sha256:", 1)[1]
        assert len(digest) == 64
        assert digest == digest.lower()
        assert re.fullmatch(r"[0-9a-f]{64}", digest), f"{name} digest is not hex"


def test_repositories_are_fully_qualified(lock: dict[str, str], candidates: dict) -> None:
    """An unqualified name resolves through the client's registry list.

    That list is not a property of this repository, so the same lock could
    mean different images on two machines.
    """
    for name in candidates["images"]:
        repository = lock[name].split(":", 1)[0]
        assert "/" in repository, f"{name} is not fully qualified: {repository}"
        assert repository.split("/", 1)[0] in {"docker.io", "ghcr.io", "quay.io", "registry.k8s.io"}


def test_no_placeholder_value_survives(lock: dict[str, str]) -> None:
    for name, value in lock.items():
        assert "<" not in value and ">" not in value, f"{name} contains a placeholder"
        assert value.strip() == value, f"{name} has surrounding whitespace"
        assert value, f"{name} is empty"


def test_variable_names_are_shell_safe(lock: dict[str, str]) -> None:
    for name in lock:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", name), name


def test_no_duplicate_variables() -> None:
    names = [
        line.split("=", 1)[0]
        for line in LOCK.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(names) == len(set(names))


def test_required_metadata_is_present(lock: dict[str, str]) -> None:
    for required in (
        "APG_LOCK_FORMAT",
        "APG_VERSIONS_IN_SHA256",
        "APG_LOCKED_AT",
        "TARGET_PLATFORM",
        "PYTHON_VERSION",
        "COMPOSE_MINIMUM_VERSION",
    ):
        assert required in lock, f"missing {required}"


def test_target_platform_is_declared_and_matches(lock: dict[str, str], candidates: dict) -> None:
    assert lock["TARGET_PLATFORM"] == candidates["target_platform"]
    assert re.fullmatch(r"linux/(amd64|arm64)", lock["TARGET_PLATFORM"])


def test_python_version_agrees_with_the_pinned_interpreter(lock: dict[str, str]) -> None:
    """Plan decision H: .python-version is authoritative for local tooling."""
    pinned = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert lock["PYTHON_VERSION"] == pinned


def test_every_candidate_image_is_locked(lock: dict[str, str], candidates: dict) -> None:
    for name in candidates["images"]:
        assert name in lock, f"{name} is declared but not locked"
    for name in candidates["packages"]:
        assert name in lock, f"{name} is declared but not locked"


def test_locked_reference_matches_the_declared_candidate(
    lock: dict[str, str], candidates: dict
) -> None:
    for name, reference in candidates["images"].items():
        assert lock[name].rsplit("@", 1)[0] == reference, name


# ---------------------------------------------------------------------------
# --check actually detects things
# ---------------------------------------------------------------------------


def test_check_passes_on_the_committed_lock() -> None:
    result = subprocess.run([str(SCRIPT), "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_check_makes_no_network_call() -> None:
    """Offline by construction: everything it verifies is on disk.

    Proven by running it with an unreachable Docker host and no proxy; a
    registry call would fail rather than pass.
    """
    result = subprocess.run(
        [str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:" + str(REPO_ROOT / ".venv" / "bin"),
            "HOME": "/nonexistent",
            "DOCKER_HOST": "tcp://127.0.0.1:1",
            "http_proxy": "http://127.0.0.1:1",
            "https_proxy": "http://127.0.0.1:1",
        },
    )
    assert result.returncode == 0, result.stderr


def test_check_detects_an_edited_candidate_file(fake_repo: Path) -> None:
    candidates = fake_repo / "versions.in.yaml"
    candidates.write_text(
        candidates.read_text(encoding="utf-8").replace("pg18", "pg17"), encoding="utf-8"
    )
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "versions.in.yaml has changed" in result.stderr


def test_check_detects_a_floating_tag(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    text = lock_path.read_text(encoding="utf-8")
    text = re.sub(
        r"^TRAEFIK_IMAGE=.*$",
        "TRAEFIK_IMAGE=docker.io/library/traefik:latest@sha256:" + "0" * 64,
        text,
        flags=re.MULTILINE,
    )
    lock_path.write_text(text, encoding="utf-8")
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "floating tag" in result.stderr


def test_check_detects_a_missing_digest(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    text = re.sub(
        r"^TRAEFIK_IMAGE=.*$",
        "TRAEFIK_IMAGE=docker.io/library/traefik:v3.7",
        lock_path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    lock_path.write_text(text, encoding="utf-8")
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "sha256" in result.stderr


def test_check_detects_a_removed_image(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    text = "\n".join(
        line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("POSTGRES_IMAGE=")
    )
    lock_path.write_text(text + "\n", encoding="utf-8")
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "POSTGRES_IMAGE" in result.stderr


def test_check_detects_a_duplicate_variable(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8") + "TARGET_PLATFORM=linux/arm64\n", encoding="utf-8"
    )
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "duplicate variable" in result.stderr


def test_check_detects_a_stale_extra_variable(fake_repo: Path) -> None:
    """A variable removed from the candidate file must not survive in the lock."""
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8")
        + "OBSOLETE_IMAGE=docker.io/x/y:1@sha256:"
        + "a" * 64
        + "\n",
        encoding="utf-8",
    )
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "OBSOLETE_IMAGE" in result.stderr


def test_check_detects_a_python_version_mismatch(fake_repo: Path) -> None:
    (fake_repo / ".python-version").write_text("3.11.0\n", encoding="utf-8")
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "python-version" in result.stderr


def test_check_reports_a_missing_lock_file(fake_repo: Path) -> None:
    (fake_repo / "versions.env").unlink()
    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "missing" in result.stderr


# ---------------------------------------------------------------------------
# The lock and the generated project namespace must not collide
# ---------------------------------------------------------------------------


def test_lock_variables_do_not_overlap_generated_ones(lock: dict[str, str]) -> None:
    """Runbook §6.4: an overlap would make --env-file ordering load-bearing.

    The generated set is read from the renderer rather than restated here, so a
    key added to ``compose.env`` is covered the moment it is added.
    """
    from agentic_postgres import rendering

    assert not set(rendering.COMPOSE_ENV_KEYS) & set(lock)


def test_lock_variables_do_not_overlap_the_edge_env(lock: dict[str, str]) -> None:
    """The third env file of ADR 0013 needs the same disjointness."""
    from agentic_postgres import host_config

    assert not set(host_config.EDGE_COMPOSE_ENV_KEYS) & set(lock)


# ---------------------------------------------------------------------------
# Feature floors (Session 2)
# ---------------------------------------------------------------------------


def test_the_traefik_floor_is_recorded(lock: dict[str, str], candidates: dict) -> None:
    """A floor that is not in the lock cannot be checked offline."""
    declared = candidates["feature_floors"]["TRAEFIK_MINIMUM_VERSION"]
    assert lock["TRAEFIK_MINIMUM_VERSION"] == declared
    tag = lock["TRAEFIK_IMAGE"].rsplit("@", 1)[0].rsplit(":", 1)[-1].lstrip("v")
    assert lock["TRAEFIK_VERSION"] == tag


def test_a_version_below_the_floor_is_detected(fake_repo: Path) -> None:
    """The floor exists to stop a downgrade that silently breaks discovery.

    This docstring used to say the floor guarded
    ``accessLog.fields.queryParameters.defaultMode``, a key that exists in no
    Traefik version (ADR 0019). The floor was real and its justification was
    invented, which is the failure mode a floor is least able to notice about
    itself.

    What it guards now was measured: Traefik 3.5 and below ask the Docker daemon
    for API v1.24, Docker 29 answers 400 to anything below 1.40, and the Docker
    provider never loads -- the edge comes up healthy and routes nothing.
    """
    lock_path = fake_repo / "versions.env"
    text = (
        lock_path.read_text(encoding="utf-8")
        .replace("traefik:v3.7@", "traefik:v2.9@")
        .replace("TRAEFIK_VERSION=3.7", "TRAEFIK_VERSION=2.9")
    )
    lock_path.write_text(text, encoding="utf-8")

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "does not support a feature" in result.stderr


def test_a_resolved_version_that_disagrees_with_the_tag_is_detected(fake_repo: Path) -> None:
    """Otherwise the floor is satisfied by editing one number.

    ``TRAEFIK_VERSION`` is derived from the image tag by ``--update``. If
    ``--check`` compared the floor against it without also comparing it against
    the tag, raising the recorded version past the floor would be a one-line
    edit that changes nothing about what runs.
    """
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace("TRAEFIK_VERSION=3.7", "TRAEFIK_VERSION=9.9"),
        encoding="utf-8",
    )

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "is tagged" in result.stderr


def test_a_missing_floor_is_detected(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        "\n".join(
            line
            for line in lock_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("TRAEFIK_MINIMUM_VERSION=")
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "TRAEFIK_MINIMUM_VERSION" in result.stderr


def test_cli_grammar() -> None:
    assert subprocess.run([str(SCRIPT), "--help"], capture_output=True, check=False).returncode == 0
    assert subprocess.run([str(SCRIPT)], capture_output=True, check=False).returncode == 2
    assert (
        subprocess.run([str(SCRIPT), "--bogus"], capture_output=True, check=False).returncode == 2
    )


# ---------------------------------------------------------------------------
# Packages are dereferenced, not copied through (ADR 0077, lock format 2)
# ---------------------------------------------------------------------------

PACKAGE_DIGEST = re.compile(r"^(sha256|sha512):[A-Za-z0-9+/=_\-]{32,}$")
KNOWN_REGISTRIES = {"pypi", "npm", "apt"}

#: Keys a registry needs BEYOND the three every entry carries. Session 10.
#:
#: `apt` needs `index` because a Debian archive has no per-package endpoint the
#: way PyPI and npm do -- the whole suite is one file, and which file depends on
#: the base image's release. PyPI and npm are declared with empty sets rather
#: than omitted, so a registry added without deciding this fails the
#: completeness assertion below instead of defaulting to "no extra keys".
#:
#: This mirrors `REGISTRY_KEYS` in `bin/lock-versions.sh`, and the duplication is
#: real: that one lives inside an embedded Python program a test cannot import.
#: `test_the_lock_script_knows_every_registry_this_module_does` is what keeps
#: the two from drifting, because two lists that must agree and nothing
#: comparing them is D536's shape and it is one session old.
REGISTRY_EXTRA_KEYS: dict[str, set[str]] = {"pypi": set(), "npm": set(), "apt": {"index"}}


def test_every_package_declares_a_registry_and_a_package_name(candidates: dict) -> None:
    """Format 2's whole point: an entry the lock can look up.

    Before this, a `packages:` entry was `NAME: "version"` -- a string with no
    registry and no package name, so there was nothing to dereference even in
    principle. `SCALAR_VERSION: "1.36.4"` named a release that has never existed
    and survived four sessions of a green check (D201).
    """
    assert candidates["lock_format"] >= 2
    assert set(REGISTRY_EXTRA_KEYS) == KNOWN_REGISTRIES, (
        "a registry was added to one of these and not the other, so an entry's "
        "required key set would be decided by a dict that does not know about it"
    )
    for name, entry in candidates["packages"].items():
        assert isinstance(entry, dict), f"{name} is a bare version string, not a format-2 entry"
        assert entry.get("registry") in KNOWN_REGISTRIES, (
            f"{name} declares {entry.get('registry')!r}"
        )
        expected = {"registry", "package", "version"} | REGISTRY_EXTRA_KEYS[entry["registry"]]
        assert set(entry) == expected, f"{name}: {sorted(entry)} != {sorted(expected)}"
        assert entry["package"], name
        assert str(entry["version"]), name


def test_the_lock_script_knows_every_registry_this_module_does() -> None:
    """The two lists that must agree, related rather than reviewed.

    `bin/lock-versions.sh` carries its validator inside an embedded Python
    program, so this module cannot import its `REGISTRIES` tuple and has to
    restate it. D536 is one session old and is exactly this shape -- two
    hand-written lists of the same thing with nothing comparing them -- so the
    comparison is written at the same time as the second list rather than after
    something drifts.

    A source scan rather than an execution, because the script's checker is not
    reachable as a function. That is weaker than calling it, and it is stated:
    what this catches is a registry added here and not there, which is the
    failure that actually happens.
    """
    source = (REPO_ROOT / "bin" / "lock-versions.sh").read_text(encoding="utf-8")
    for registry in sorted(KNOWN_REGISTRIES):
        assert f'"{registry}"' in source, (
            f"this module accepts registry {registry!r} and bin/lock-versions.sh "
            "never mentions it, so --update cannot dereference it"
        )
    for registry, extra in REGISTRY_EXTRA_KEYS.items():
        for key in sorted(extra):
            assert f'"{key}"' in source, (
                f"{registry} entries declare {key!r} and the lock script does not "
                "read it, so the value would be ignored"
            )


def test_every_package_carries_an_artifact_digest(lock: dict[str, str], candidates: dict) -> None:
    """The digest is what a copied string could never have.

    It is not proof the artifact exists *today* -- `--check` makes no network
    call, deliberately, so that it cannot pass merely because a registry is up.
    It is proof that whoever ran `--update` resolved the version to exactly one
    published artifact: an sdist on PyPI, a tarball on npm.
    """
    for name in candidates["packages"]:
        digest = lock.get(f"{name}_DIGEST")
        assert digest is not None, f"{name} has no artifact digest; run --update"
        assert PACKAGE_DIGEST.match(digest), f"{name}_DIGEST is malformed: {digest!r}"


def test_no_orphan_digest_survives_a_removed_package(
    lock: dict[str, str], candidates: dict
) -> None:
    """A stale `_DIGEST` would name an artifact for a package nobody declares."""
    declared = {f"{name}_DIGEST" for name in candidates["packages"]}
    orphans = {name for name in lock if name.endswith("_DIGEST")} - declared
    assert not orphans, f"versions.env carries digests for undeclared packages: {sorted(orphans)}"


def test_a_package_with_no_digest_is_detected(fake_repo: Path) -> None:
    """The failure this exists to catch, injected: a version nothing resolved."""
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        "\n".join(
            line
            for line in lock_path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("PWDLIB_VERSION_DIGEST=")
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "PWDLIB_VERSION_DIGEST" in result.stderr
    assert "D201" in result.stderr, (
        "the message should name the defect it prevents; an operator who sees this "
        "is one `--update` away from the whole story"
    )


def test_a_malformed_digest_is_detected(fake_repo: Path) -> None:
    lock_path = fake_repo / "versions.env"
    lock_path.write_text(
        lock_path.read_text(encoding="utf-8").replace(
            "PWDLIB_VERSION_DIGEST=sha256:", "PWDLIB_VERSION_DIGEST=notanalgorithm:"
        ),
        encoding="utf-8",
    )

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "PWDLIB_VERSION_DIGEST" in result.stderr


def test_a_bare_version_string_is_refused(fake_repo: Path) -> None:
    """A format-1 entry in a format-2 file, which is what a bad merge produces."""
    candidates_path = fake_repo / "versions.in.yaml"
    document = yaml.safe_load(candidates_path.read_text(encoding="utf-8"))
    document["packages"]["PWDLIB_VERSION"] = "0.3.0"
    candidates_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    result = run_check(fake_repo)
    assert result.returncode == 5
    assert "bare version string" in result.stderr


def test_the_interpreter_is_not_moved_by_this_dependency_set(candidates: dict) -> None:
    """D240, kept as an executable statement rather than a comment.

    The Session 6 runbook specified CPython 3.13. Measured in Run 2: every
    package in this set declares `requires_python >= 3.10` or looser at the
    pinned version, so nothing forces the bump. If a later session raises
    `.python-version`, this fails and the bump gets the ADR it needs rather than
    arriving inside an unrelated commit.
    """
    assert candidates["python"]["version"].startswith("3.12."), (
        "the interpreter moved. Nothing in the Session 6 dependency set required "
        "3.13 when it was measured; a bump is its own decision (D240)"
    )
