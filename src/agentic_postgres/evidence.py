"""Session evidence assembled from machine-readable test artifacts.

Runbook §4.7 and Phase 12. Two rules shape this module:

**It fails rather than guesses.** Every number comes from a parsed artifact. If
the JUnit file is absent or malformed, evidence generation fails — it does not
emit a zero. A hand-entered or defaulted count is worse than no evidence,
because it looks like a measurement.

**It records the tested source commit, not its own.** A committed evidence file
cannot contain the hash of the commit containing itself. ``source_commit`` is
the clean commit that was tested; the evidence file is a generated, ignored
artifact.
"""

from __future__ import annotations

import json
import re
import subprocess
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import REPO_ROOT

EVIDENCE_SCHEMA_VERSION = 1

#: Tags that would mean an image is not actually pinned.
FLOATING_TAGS = {"latest", "main", "master", "edge", "stable", "nightly", "dev"}

#: Fields that must differ between any two rendered projects (runbook §8).
ISOLATED_FIELDS = (
    ("project", "key"),
    ("project", "domain"),
    ("project", "generated_directory"),
    ("compose", "project_name"),
    ("compose", "networks", "edge"),
    ("compose", "networks", "internal"),
    ("compose", "volumes", "postgres"),
    ("database", "name"),
    ("jwt", "issuer"),
    ("jwt", "audience"),
    ("secrets", "namespace"),
    ("storage", "bucket"),
    ("storage", "prefix"),
    ("backup", "stanza"),
    ("backup", "repository_prefix"),
)


class EvidenceError(RuntimeError):
    """A required input could not be parsed. Evidence is not written."""


def _read(path: Path) -> str:
    if not path.is_file():
        raise EvidenceError(f"required evidence input is missing: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------


def git_output(*args: str) -> str:
    # S603/S607 suppressed narrowly: src/ is not in the shell-out ignore list
    # because library code generally should not spawn processes. Evidence must
    # record the tested commit, and git is the only source of that. Arguments
    # are literals from this module, never operator input.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EvidenceError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def assert_clean_tree() -> None:
    """Evidence describes a specific commit, so the tree must be that commit."""
    if git_output("status", "--porcelain"):
        raise EvidenceError(
            "the working tree is not clean; evidence must describe a committed state"
        )


# ---------------------------------------------------------------------------
# Test artifacts
# ---------------------------------------------------------------------------


def parse_junit(path: Path) -> dict[str, int]:
    """Read counts from JUnit XML rather than from pytest's terminal output."""
    # S314: the input is JUnit XML this repository's own pytest run produced
    # moments earlier, under a path the gate controls. It is not untrusted
    # input, and adding defusedxml would widen the hash-locked dependency set
    # for no reduction in real risk.
    try:
        root = ElementTree.fromstring(_read(path))  # noqa: S314
    except ElementTree.ParseError as exc:
        raise EvidenceError(f"{path} is not parseable JUnit XML: {exc}") from exc

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise EvidenceError(f"{path} contains no testsuite element")

    totals = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for suite in suites:
        try:
            tests = int(suite.attrib["tests"])
            failures = int(suite.attrib.get("failures", 0))
            errors = int(suite.attrib.get("errors", 0))
            skipped = int(suite.attrib.get("skipped", 0))
        except (KeyError, ValueError) as exc:
            raise EvidenceError(f"{path} has malformed testsuite attributes: {exc}") from exc

        totals["failed"] += failures
        totals["errors"] += errors
        totals["skipped"] += skipped
        totals["passed"] += tests - failures - errors - skipped

    return totals


def parse_collection(path: Path) -> int:
    """Count collected node IDs in a `pytest --collect-only -q` artifact."""
    lines = [
        line.strip()
        for line in _read(path).splitlines()
        if line.strip().startswith("tests/") and "::" in line
    ]
    if not lines:
        raise EvidenceError(f"{path} contains no collected node IDs")
    return len(lines)


def count_future_placeholders() -> int:
    """Count ``future`` markers by parsing the test sources with ast."""
    import ast

    total = 0
    for path in sorted((REPO_ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "future"
                ):
                    total += 1
    return total


# ---------------------------------------------------------------------------
# Rendered projects
# ---------------------------------------------------------------------------


def load_rendered() -> dict[str, dict[str, Any]]:
    generated = REPO_ROOT / ".generated"
    rendered: dict[str, dict[str, Any]] = {}
    for directory in sorted(generated.iterdir()):
        if directory.name.startswith(".") or not directory.is_dir():
            continue
        outputs = directory / "outputs.json"
        if not outputs.is_file():
            continue
        rendered[directory.name] = json.loads(outputs.read_text(encoding="utf-8"))

    if not rendered:
        raise EvidenceError("no rendered project was found under .generated/")
    return rendered


def at(document: dict[str, Any], pointer: tuple[str, ...]) -> Any:
    value: Any = document
    for key in pointer:
        value = value[key]
    return value


def collision_count(rendered: dict[str, dict[str, Any]]) -> int:
    """Compare parsed semantic fields, never duplicate strings (runbook §8)."""
    documents = list(rendered.values())
    collisions = 0
    for index, left in enumerate(documents):
        for right in documents[index + 1 :]:
            for pointer in ISOLATED_FIELDS:
                if at(left, pointer) == at(right, pointer):
                    collisions += 1
            for role, name in left["database"]["roles"].items():
                if right["database"]["roles"][role] == name:
                    collisions += 1
    return collisions


def floating_image_references() -> int:
    count = 0
    for line in _read(REPO_ROOT / "versions.env").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if not name.endswith("_IMAGE"):
            continue
        if "@sha256:" not in value:
            count += 1
            continue
        tag = value.rsplit("@", 1)[0].rsplit(":", 1)[-1]
        if tag.lower() in FLOATING_TAGS:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Tool versions
# ---------------------------------------------------------------------------

_REDACT = re.compile(r"(sk-|ghp_|gho_|Bearer\s+)\S+", re.IGNORECASE)


def tool_version(*command: str) -> str | None:
    """Capture one tool's version, redacted, or None if it is unavailable."""
    try:
        # S603: `command` comes only from the literal probe table below.
        result = subprocess.run(  # noqa: S603
            command, capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    first = (result.stdout or result.stderr).strip().splitlines()
    return _REDACT.sub("[REDACTED]", first[0]) if first else None


def tool_versions() -> dict[str, str]:
    probes = {
        "git": ("git", "--version"),
        "python": ("python", "--version"),
        "docker": ("docker", "--version"),
        "docker_compose": ("docker", "compose", "version", "--short"),
        "shellcheck": ("shellcheck", "--version"),
        "jq": ("jq", "--version"),
    }
    return {
        name: version
        for name, command in probes.items()
        if (version := tool_version(*command)) is not None
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build(session: int, artifacts: Path) -> dict[str, Any]:
    assert_clean_tree()

    contract_tests = parse_junit(artifacts / "contract-tests.xml")
    p0_collected = parse_collection(artifacts / "p0-collection.txt")
    rendered = load_rendered()

    registry = yaml.safe_load(_read(REPO_ROOT / "tests" / "acceptance-registry.yaml"))
    if not registry:
        raise EvidenceError("the acceptance registry is empty")

    first = next(iter(rendered.values()))
    collisions = collision_count(rendered)
    floating = floating_image_references()

    passed = (
        contract_tests["failed"] == 0
        and contract_tests["errors"] == 0
        and collisions == 0
        and floating == 0
    )

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "session": session,
        "status": "passed" if passed else "failed",
        "source_commit": git_output("rev-parse", "HEAD"),
        "source_tree": git_output("rev-parse", "HEAD^{tree}"),
        "source_specification_sha256": first["inputs"]["source_specification_sha256"],
        "project_manifest_sha256": {
            key: document["inputs"]["project_sha256"] for key, document in sorted(rendered.items())
        },
        "capabilities_sha256": first["inputs"]["capabilities_sha256"],
        "versions_lock_sha256": first["inputs"]["versions_lock_sha256"],
        "rendered_projects": sorted(rendered),
        "project_scoped_collision_count": collisions,
        "contract_tests": contract_tests,
        "p0_tests_collected": p0_collected,
        "p0_tests_future": count_future_placeholders(),
        "registered_requirements": len(registry),
        "floating_image_references": floating,
        "outputs_schema_version": first["schema_version"],
        "tool_versions": tool_versions(),
        "completed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
