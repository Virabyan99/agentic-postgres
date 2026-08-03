#!/usr/bin/env python
"""Generate the acceptance matrix and the product-contract requirement table.

Both artifacts are derived from ``tests/acceptance-registry.yaml``, which is
the only place a requirement ID is created. Hand-maintaining them alongside the
registry would drift, and the failure mode is silent: a P0 requirement listed in
prose that no test covers. Generating them makes that structurally impossible
rather than merely detectable — the table cannot contain a requirement the
registry lacks, because the registry produced it.

``--check`` never writes. The Session 1 gate demands a clean tree before it
runs, so a generator that self-healed mid-gate would dirty the tree it just
required be clean. Drift is corrected at commit time by the pre-commit hook and
merely confirmed by the gate.

Exit codes:
    0  success
    5  generated documentation has drifted
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

REGISTRY = REPO_ROOT / "tests" / "acceptance-registry.yaml"
MATRIX = REPO_ROOT / "docs" / "acceptance-matrix.md"
CONTRACT = REPO_ROOT / "docs" / "product-contract.md"

BEGIN = "<!-- BEGIN GENERATED: requirements -->"
END = "<!-- END GENERATED: requirements -->"

AREAS = {
    "DEP": "Deployment, bootstrap, and project isolation",
    "CFG": "Manifests, naming, rendering, and generated configuration",
    "DBX": "Database endpoints and client compatibility",
    "SEC": "Authorization, credentials, and security boundaries",
    "API": "PostgREST and FastAPI contracts",
    "AGT": "MCP and agent behavior",
    "STO": "Object storage",
    "REC": "Backup and recovery",
    "OPS": "Health, diagnostics, logging, and operations",
    "DX": "Developer experience and documentation",
}


def load_registry() -> list[dict[str, Any]]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def one_line(text: str) -> str:
    return " ".join(text.split())


def render_matrix(registry: list[dict[str, Any]]) -> str:
    by_session: dict[int, list[dict[str, Any]]] = {}
    for entry in registry:
        by_session.setdefault(entry["target_session"], []).append(entry)

    total = len(registry)
    p0 = sum(1 for entry in registry if entry["priority"] == "P0")
    active = sum(1 for entry in registry if entry["target_session"] == 1)

    lines = [
        "# Acceptance matrix",
        "",
        "<!-- GENERATED FILE. Do not hand-edit.",
        "     Source: tests/acceptance-registry.yaml",
        "     Regenerate: python bin/render-acceptance-matrix.py --write",
        "     Verified in CI: python bin/render-acceptance-matrix.py --check -->",
        "",
        "Every requirement below has at least one Pytest node ID that pytest can",
        "actually collect. That is checked by running a real collection and",
        "comparing node IDs, not by searching files for function names — a text",
        "search passes on a commented-out test.",
        "",
        f"**{total} requirements** — {p0} P0, {active} active in Session 1, "
        f"{total - active} owned by later sessions.",
        "",
        "## By session",
        "",
        "| Session | Requirements | Status |",
        "|---:|---:|---|",
    ]

    for session in sorted(by_session):
        count = len(by_session[session])
        status = "active" if session == 1 else f"placeholders owned by Session {session}"
        lines.append(f"| {session} | {count} | {status} |")

    lines += ["", "## Requirements", ""]

    for session in sorted(by_session):
        lines += [
            f"### Session {session}",
            "",
            "| ID | Priority | Guarantee | Proof |",
            "|---|---|---|---|",
        ]
        for entry in sorted(by_session[session], key=lambda e: e["id"]):
            proofs = "<br>".join(f"`{node}`" for node in entry["test_nodeids"])
            lines.append(
                f"| `{entry['id']}` | {entry['priority']} | "
                f"{one_line(entry['description'])} | {proofs} |"
            )
        lines.append("")

    lines += [
        "## Requirement ID prefixes",
        "",
        "| Prefix | Area |",
        "|---|---|",
    ]
    used = {entry["id"].split("-", 1)[0] for entry in registry}
    for prefix, area in AREAS.items():
        marker = "" if prefix in used else " *(unused so far)*"
        lines.append(f"| `{prefix}` | {area}{marker} |")

    lines.append("")
    return "\n".join(lines)


def render_requirements_block(registry: list[dict[str, Any]]) -> str:
    lines = [
        BEGIN,
        "<!-- Generated from tests/acceptance-registry.yaml by",
        "     bin/render-acceptance-matrix.py --write. Do not hand-edit. -->",
        "",
    ]

    for priority in ("P0", "P1", "P2"):
        entries = sorted(
            (e for e in registry if e["priority"] == priority),
            key=lambda e: (e["target_session"], e["id"]),
        )
        if not entries:
            continue
        lines += [
            f"**{priority} — {len(entries)} requirements**",
            "",
            "| ID | Session | Guarantee |",
            "|---|---:|---|",
        ]
        lines += [
            f"| `{entry['id']}` | {entry['target_session']} | {one_line(entry['description'])} |"
            for entry in entries
        ]
        lines.append("")

    lines += [
        "Full node IDs are in [the acceptance matrix](acceptance-matrix.md).",
        "",
        END,
    ]
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    start, end = text.find(BEGIN), text.find(END)
    if start == -1 or end == -1:
        raise SystemExit(f"markers not found in {CONTRACT}")
    return text[:start] + block + text[end + len(END) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bin/render-acceptance-matrix.py",
        description="Generate or verify documentation derived from the acceptance registry.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Update the generated documents.")
    group.add_argument("--check", action="store_true", help="Fail on drift; write nothing.")
    args = parser.parse_args(argv)

    registry = load_registry()
    wanted = {
        MATRIX: render_matrix(registry),
        CONTRACT: replace_block(
            CONTRACT.read_text(encoding="utf-8"), render_requirements_block(registry)
        ),
    }

    drifted: list[Path] = []
    for path, content in wanted.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if args.write:
            path.write_text(content, encoding="utf-8")
            print(f"render-acceptance-matrix: updated {path.relative_to(REPO_ROOT)}")
        else:
            drifted.append(path)

    if drifted:
        print(
            "render-acceptance-matrix: generated documentation has drifted from "
            "tests/acceptance-registry.yaml:",
            file=sys.stderr,
        )
        for path in drifted:
            print(f"  - {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        print(
            "Run: python bin/render-acceptance-matrix.py --write",
            file=sys.stderr,
        )
        return 5

    if args.check:
        print(
            f"render-acceptance-matrix: generated documentation is current "
            f"({len(registry)} requirements)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
