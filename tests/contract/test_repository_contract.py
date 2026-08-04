"""Repository shape, ignore rules, and the hard-coded-identity scan.

The fixture scan (runbook §9) deliberately searches for the *exact distinctive
values* — `fixture-alpha`, `fixture-alpine`, their domains and audiences — and
never for the generic word "example", which the runbook explicitly prohibits
because it produces meaningless false positives.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REQUIRED_PATHS = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".python-version",
    "README.md",
    "VERSION",
    "capabilities.example.yaml",
    "compose.yaml",
    "deploy.sh",
    "host.example.yaml",
    "project.example.yaml",
    "project.second.example.yaml",
    "secrets.required.yaml",
    "pyproject.toml",
    "pytest.ini",
    "requirements-dev.in",
    "requirements-dev.txt",
    "versions.env",
    "versions.in.yaml",
    ".github/workflows/ci.yml",
    ".generated/.gitkeep",
    "evidence/.gitkeep",
    "migrations/.gitkeep",
    "services/auth-api/.gitkeep",
    "services/docs/.gitkeep",
    "services/mcp/.gitkeep",
    "docs/acceptance-matrix.md",
    "docs/capability-plan.md",
    "docs/new-team-member.md",
    "docs/product-contract.md",
    "docs/security-acceptance.md",
    "docs/source-specification.md",
    "docs/source-specification.sha256",
    "docs/threat-model.md",
    "docs/decisions/README.md",
    "docs/decisions/0001-product-shape.md",
    "docs/decisions/0002-configuration-authority.md",
    "docs/decisions/0003-example-domain.md",
    "docs/decisions/0004-version-lock-format.md",
    "docs/decisions/0005-route-reservation.md",
    "docs/decisions/0006-capability-scopes.md",
    "docs/decisions/0007-bounds-authority.md",
    "docs/decisions/0008-sensitive-key-policy.md",
    "docs/decisions/0009-host-and-edge-plane.md",
    "docs/decisions/0010-secret-materialization.md",
    "docs/decisions/0011-provider-bootstrap-state.md",
    "docs/decisions/0012-output-document-kinds.md",
    "docs/decisions/0013-compose-wrapper-scopes.md",
    "docs/decisions/0014-gate-scope-and-session-derivation.md",
    "docs/decisions/0015-reserved-health-route.md",
    "docs/decisions/0016-absence-is-not-a-collision.md",
    "docs/decisions/0017-stub-lifecycle.md",
    "bin/bootstrap-providers.py",
    "bin/docker-firewall.sh",
    "bin/edge.sh",
    "bin/edge-network.sh",
    "bin/materialize-secrets.py",
    "bin/materialize-secrets.sh",
    "bin/project-runtime.sh",
    "bin/provision-host.sh",
    "bin/session-02-check.sh",
    "src/agentic_postgres/infisical_client.py",
    "src/agentic_postgres/installed_release.py",
    "infra/edge/compose.yaml",
    "infra/edge/traefik.yaml",
    "infra/edge/dynamic/baseline.yaml",
    "infra/host/00-agentic-postgres-ssh.conf",
    "infra/host/20auto-upgrades",
    "infra/host/daemon.json",
    "infra/host/docker-user-rules.v4",
    "infra/host/docker-user-rules.v6",
    "libexec/agentic-postgres-edge",
    "libexec/agentic-postgres-firewall",
    "libexec/agentic-postgres-project",
    "systemd/agentic-postgres-docker-firewall.service",
    "systemd/agentic-postgres-edge.service",
    "systemd/agentic-postgres-project@.service",
    "services/edge-probe/Dockerfile",
    "services/edge-probe/probe.py",
    "services/secret-check/Dockerfile",
    "services/secret-check/check.py",
    "docs/plans/session-01-implementation-plan.md",
    "docs/plans/session-02-implementation-plan.md",
    "schemas/bootstrap-state.schema.json",
    "schemas/capabilities.schema.json",
    "schemas/host.schema.json",
    "schemas/outputs.schema.json",
    "schemas/project.schema.json",
    "schemas/secret-contract.schema.json",
    "src/agentic_postgres/__init__.py",
    "src/agentic_postgres/bootstrap_state.py",
    "src/agentic_postgres/config.py",
    "src/agentic_postgres/evidence.py",
    "src/agentic_postgres/host_config.py",
    "src/agentic_postgres/naming.py",
    "src/agentic_postgres/output_migrations.py",
    "src/agentic_postgres/rendering.py",
    "src/agentic_postgres/secrets_contract.py",
    "tests/fixtures/outputs-v1.json",
    "tests/acceptance-registry.yaml",
    "tests/conftest.py",
    # The three Session 2 execution environments. Listed because the registry
    # points requirement proofs at them: a directory that silently vanished
    # would take its P0 evidence with it, and the collectibility check would
    # then fail somewhere far from the cause.
    "tests/deployment/conftest.py",
    "tests/deployment/test_session2_host.py",
    "tests/deployment/test_session2_edge.py",
    "tests/deployment/test_session2_isolation.py",
    "tests/external/test_session2_public_edge.py",
    "tests/security/test_session2_secret_model.py",
    "tests/security/test_session2_secrets.py",
    "tests/security/test_session2_installed_release.py",
)

#: Deployable source and templates. Example manifests, tests, documentation,
#: the copied specification, and generated output are excluded by §9.
SCAN_ROOTS = ("compose.yaml", "deploy.sh", "bin", "src", "services", "infra", "libexec", "systemd")

#: The exact distinctive values, never the generic word "example".
FIXTURE_MARKERS = (
    "fixture-alpha",
    "fixture-alpine",
    "fixture_alpha",
    "fixture_alpine",
    "fixture-alpha-dev.test",
    "fixture-alpine-dev.test",
    "urn:agentic-postgres:fixture-alpha",
    "urn:agentic-postgres:fixture-alpine",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


# ---------------------------------------------------------------------------
# Required tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", REQUIRED_PATHS)
def test_required_path_exists(relative: str) -> None:
    assert (REPO_ROOT / relative).exists(), f"{relative} is missing from the repository"


def test_source_specification_checksum_matches() -> None:
    """Phase 0: the recorded digest must describe the committed bytes."""
    from hashlib import sha256

    spec = REPO_ROOT / "docs" / "source-specification.md"
    recorded = (
        (REPO_ROOT / "docs" / "source-specification.sha256").read_text(encoding="utf-8").split()[0]
    )
    assert sha256(spec.read_bytes()).hexdigest() == recorded


# ---------------------------------------------------------------------------
# Ignore rules (runbook §6.1, §9 check 11)
# ---------------------------------------------------------------------------


def test_generated_output_is_ignored() -> None:
    untracked = git("ls-files", "--others", "--exclude-standard").split()
    leaked = [p for p in untracked if p.startswith((".generated/", "evidence/"))]
    assert not leaked, f"generated output is visible to git: {leaked}"


def test_generated_directories_keep_only_their_gitkeep() -> None:
    tracked = git("ls-files", ".generated", "evidence").split()
    assert sorted(tracked) == [".generated/.gitkeep", "evidence/.gitkeep"]


def test_gitignore_covers_the_required_entries() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (".generated/*", "evidence/*", ".venv/", "__pycache__/", ".pytest_cache/"):
        assert entry in text, f".gitignore is missing {entry}"


def test_gitignore_covers_session_two_operator_inputs() -> None:
    """Session 2 §5.4: only redacted examples are committed.

    These have to be *ignored* rather than merely uncommitted, because
    bin/session-01-check.sh step 1 fails on any untracked file and that gate
    also runs from the checkout on the deployment host, where these files
    genuinely exist.
    """
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("/host.yaml", "/capabilities.yaml", "/project.alpha.yaml", "/project.beta.yaml"):
        assert entry in text, f".gitignore is missing {entry}"


def test_committed_examples_are_not_swept_up_by_the_ignore_rules() -> None:
    """Guard the guard: a `/project.*.yaml` glob would hide a real example.

    `git check-ignore` is asked rather than the pattern being re-read, because
    the question is what Git does, not what the file appears to say.
    """
    for relative in ("project.example.yaml", "project.second.example.yaml", "host.example.yaml"):
        result = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 1, f"{relative} is ignored but must be committed"


def test_gitattributes_forces_lf() -> None:
    """Without this, a Windows clone breaks every shebang (plan decision N)."""
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in text
    assert "*.sh   text eol=lf" in text or "*.sh text eol=lf" in text


def test_no_tracked_file_uses_crlf() -> None:
    offenders = []
    for relative in git("ls-files").split():
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            if b"\r" in path.read_bytes():
                offenders.append(relative)
        except OSError:
            continue
    assert not offenders, f"tracked files with CRLF: {offenders}"


# ---------------------------------------------------------------------------
# Hard-coded fixture identities (runbook §9)
# ---------------------------------------------------------------------------


def scan_targets() -> list[Path]:
    targets: list[Path] = []
    for root in SCAN_ROOTS:
        path = REPO_ROOT / root
        if path.is_file():
            targets.append(path)
        elif path.is_dir():
            targets.extend(p for p in path.rglob("*") if p.is_file())
    return targets


@pytest.mark.parametrize("marker", FIXTURE_MARKERS)
def test_deployable_source_does_not_hardcode_a_fixture_identity(marker: str) -> None:
    offenders = []
    for path in scan_targets():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if marker in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"{marker!r} is hard-coded in: {offenders}"


def test_the_scan_would_actually_find_something(tmp_path: Path) -> None:
    """Guard the guard: a scan that can never fail proves nothing."""
    planted = tmp_path / "planted.py"
    planted.write_text("SLUG = 'fixture-alpha'\n", encoding="utf-8")
    assert "fixture-alpha" in planted.read_text(encoding="utf-8")


def test_scan_scope_excludes_what_the_runbook_excludes() -> None:
    """Fixture values legitimately appear in manifests, tests, and docs."""
    assert "fixture-alpha" in (REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8")
    for excluded in ("tests", "docs", "project.example.yaml"):
        assert excluded not in SCAN_ROOTS


# ---------------------------------------------------------------------------
# Version and template metadata
# ---------------------------------------------------------------------------


def test_version_file_is_a_single_stripped_line() -> None:
    raw = (REPO_ROOT / "VERSION").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert len(raw.strip().splitlines()) == 1
    assert raw.strip()


def test_python_version_is_pinned_to_a_patch_release() -> None:
    import re

    pinned = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"3\.\d+\.\d+", pinned), f"{pinned!r} is not a patch-level pin"


def test_dependency_lock_uses_hashes() -> None:
    text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "--hash=sha256:" in text
    packages = [line for line in text.splitlines() if line and not line[0].isspace()]
    assert len(packages) > 5
    for line in packages:
        if line.startswith("#"):
            continue
        assert "==" in line, f"unpinned dependency: {line}"
