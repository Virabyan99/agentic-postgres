#!/usr/bin/env python
"""Validate manifests, and generate the numeric bounds documentation.

Two responsibilities, both about keeping one authority for one fact:

``--validate-only``
    Parse and validate a project and capability manifest without producing
    output. This is what ``deploy.sh`` calls before it stages anything.

``--bounds-doc``
    Regenerate the bounds table in ``docs/product-contract.md`` from
    ``schemas/project.schema.json``, which is its sole authority (plan
    decision E). ``--check`` compares without writing and is what the gate
    runs; ``--write`` updates and is what the pre-commit hook runs.

Exit codes (runbook §2 convention):
    0   success
    2   invalid operator input or manifest
    5   contract failure, or generated documentation has drifted
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import config, host_config, rendering  # noqa: E402

BEGIN = "<!-- BEGIN GENERATED: bounds -->"
END = "<!-- END GENERATED: bounds -->"
CONTRACT = REPO_ROOT / "docs" / "product-contract.md"


def render_bounds_block() -> str:
    rows = config.bounds_table()

    lines = [
        BEGIN,
        "<!-- Generated from schemas/project.schema.json by",
        "     bin/render-config.py --bounds-doc --write. Do not hand-edit. -->",
        "",
        "| Field | Minimum | Maximum | Meaning |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        minimum = "—" if row["minimum"] is None else f"{row['minimum']:,}"
        maximum = "—" if row["maximum"] is None else f"{row['maximum']:,}"
        lines.append(f"| `{row['field']}` | {minimum} | {maximum} | {row['description']} |")

    lines += [
        "",
        "Relations between these fields cannot be expressed in JSON Schema and are",
        "enforced in `src/agentic_postgres/config.py`:",
        "",
    ]
    lines += [f"- {relation}" for relation in config.CROSS_FIELD_RELATIONS]
    lines += ["", END]
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1:
        raise SystemExit(f"markers {BEGIN} / {END} not found in {CONTRACT}")
    return text[:start] + block + text[end + len(END) :]


def bounds_doc(mode: str) -> int:
    current = CONTRACT.read_text(encoding="utf-8")
    updated = replace_block(current, render_bounds_block())

    if mode == "write":
        if updated != current:
            CONTRACT.write_text(updated, encoding="utf-8")
            print(f"render-config: updated the bounds table in {CONTRACT.name}")
        else:
            print("render-config: bounds table is already current")
        return 0

    if updated != current:
        print(
            "render-config: the bounds table in docs/product-contract.md has drifted "
            "from schemas/project.schema.json.\n"
            "Run: python bin/render-config.py --bounds-doc --write",
            file=sys.stderr,
        )
        return 5
    print("render-config: bounds table is current")
    return 0


def validate_only(project: Path, capabilities: Path) -> int:
    try:
        config.load_project_manifest(project)
    except config.ManifestError as exc:
        print(f"render-config: {project}: {exc}", file=sys.stderr)
        return 2

    try:
        config.load_capabilities_manifest(capabilities)
    except config.CapabilityContractError as exc:
        # Well formed but asserts something untrue -> contract failure, not
        # operator error.
        print(f"render-config: {capabilities}: {exc}", file=sys.stderr)
        return 5
    except config.ManifestError as exc:
        print(f"render-config: {capabilities}: {exc}", file=sys.stderr)
        return 2

    print(f"render-config: {project.name} and {capabilities.name} are valid")
    return 0


def render(project: Path, capabilities: Path) -> int:
    """Runbook §11 steps 5-15. Publishes atomically or changes nothing."""
    try:
        directory = rendering.render_project(project, capabilities)
    except config.CapabilityContractError as exc:
        print(f"deploy: {capabilities}: {exc}", file=sys.stderr)
        return 5
    except config.ManifestError as exc:
        print(f"deploy: {exc}", file=sys.stderr)
        return 2
    except rendering.RenderError as exc:
        print(f"deploy: {exc}", file=sys.stderr)
        print("deploy: the previous valid render, if any, is unchanged.", file=sys.stderr)
        return 5

    summary = (directory / "rendered-summary.txt").read_text(encoding="utf-8")
    print(summary, end="")
    print(f"\nWrote {directory}/{{outputs.json,compose.env,rendered-summary.txt}} (mode 0600)")
    print("No service was started, and no provider was contacted.")
    return 0


def edge_env(host: Path) -> int:
    """Write the shared edge stack's env file to stdout.

    Derived from ``host.yaml`` on demand rather than read from
    ``/var/lib/agentic-postgres/edge/compose.env``, so that ``--edge config``
    works offline and in CI where nothing root-owned exists. ``bin/edge.sh``
    writes identical content to that root-owned path for the systemd unit,
    which cannot read a manifest out of an operator's checkout.
    """
    try:
        document = host_config.load_host_manifest(host)
    except config.ManifestError as exc:
        print(f"render-config: {host}: {exc}", file=sys.stderr)
        return 2

    sys.stdout.buffer.write(host_config.edge_compose_env(document))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bin/render-config.py",
        description="Validate manifests and generate bounds documentation.",
    )
    parser.add_argument("--project", type=Path, help="Path to a project manifest.")
    parser.add_argument("--capabilities", type=Path, help="Path to a capability manifest.")
    parser.add_argument("--host", type=Path, help="Path to a host manifest.")
    parser.add_argument(
        "--edge-env",
        action="store_true",
        help="With --host: write the shared edge stack's compose.env to stdout.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the manifests and write nothing.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Validate, stage, verify, and publish the generated project directory.",
    )
    parser.add_argument(
        "--bounds-doc",
        action="store_true",
        help="Regenerate or verify the numeric bounds table.",
    )
    parser.add_argument("--write", action="store_true", help="With --bounds-doc: update the file.")
    parser.add_argument(
        "--check", action="store_true", help="With --bounds-doc: fail on drift, write nothing."
    )

    args = parser.parse_args(argv)

    if args.edge_env:
        if not args.host:
            parser.error("--edge-env requires --host")
        return edge_env(args.host)

    if args.bounds_doc:
        if args.write == args.check:
            parser.error("--bounds-doc requires exactly one of --write or --check")
        return bounds_doc("write" if args.write else "check")

    if args.validate_only and args.render:
        parser.error("--validate-only and --render are mutually exclusive")

    if args.validate_only or args.render:
        if not args.project or not args.capabilities:
            parser.error("--validate-only and --render require --project and --capabilities")
        if args.render:
            return render(args.project, args.capabilities)
        return validate_only(args.project, args.capabilities)

    parser.error("one of --validate-only, --render, or --bounds-doc is required")
    return 2  # unreachable; argparse exits


if __name__ == "__main__":
    raise SystemExit(main())
