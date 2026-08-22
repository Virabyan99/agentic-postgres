#!/usr/bin/env python
"""Generate the MCP tool catalog from the committed capability contract.

The catalog is what a person reads to find out what this deployment's agent
surface offers: four tools, the scopes each needs, and for the read tools the
frozen columns, filters and orderings behind them. It is derived from
``contracts/snapshots/mcp/mcp-capabilities.canonical.json`` -- the compiled,
project-neutral contract ``bin/mcp-contract.sh`` produces and checks -- for the
reason ``render-acceptance-matrix.py`` derives its tables from the registry: a
hand-maintained copy drifts, and the failure mode is silent. A catalog listing a
tool the contract does not carry, or omitting a filter it does, is a document
that tells a reader the surface is something other than what it is.

**D274 is why the checks below are what they are, and it is worth stating
because the shape here is not a web page.** `/docs/rest` was proved at 401 and
200 for four runs and had never rendered, because nothing had ever requested the
script its own markup named -- *the proof asked for the artifact's URL and never
for what the artifact then asks for*. This document names no assets. What it
names are **tool names, scope names and requirement ids**, and the check that
corresponds to fetching a page's script is asserting that every one of them
resolves against the authority that owns it: the contract for tools and scopes,
the acceptance registry for requirement ids.

The catalog is **not** served through the documentation service, and that is a
decision rather than an omission (D460). That service renders OpenAPI documents
through Scalar; a capability lock is not an OpenAPI document, and publishing one
there would need a third router and a renderer for a format Scalar does not
read. What the deployment publishes about its agent surface is the `mcp` block
of the deployed document -- the protocol revision, the accepted token use, the
contract digest and the tool count -- which is machine-readable and is already
asserted (ADR 0115, ADR 0123).

``--check`` never writes. The Session 1 gate demands a clean tree before it runs,
so a generator that self-healed mid-gate would dirty the tree it just required be
clean.

Exit codes:
    0  success
    5  generated documentation has drifted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
CATALOG = REPO_ROOT / "docs" / "mcp-tool-catalog.md"

BEGIN = "<!-- BEGIN GENERATED: mcp-catalog -->"
END = "<!-- END GENERATED: mcp-catalog -->"


def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def scope_expression(scope_sets: list[list[str]]) -> str:
    """``[[a], [b]]`` -> ``a`` OR ``b``; ``[[a, b]]`` -> ``a`` AND ``b``.

    A disjunction of conjunctions, rendered as one, because a flat list cannot
    tell "any of" from "all of" -- which is D421, and which a reader deciding
    what to grant an agent has to get right. `run_report` needs BOTH
    `notes:read` and `tasks:read`; `query_resource` needs EITHER.
    """
    if not scope_sets:
        return "—"
    alternatives = [" AND ".join(f"`{scope}`" for scope in sorted(alt)) for alt in scope_sets]
    return " OR ".join(sorted(alternatives))


def render(contract: dict[str, Any]) -> str:
    lines: list[str] = []
    tools = sorted(contract["tools"], key=lambda tool: tool["name"])

    lines.append(
        f"Contract `{contract['contract_id']}`, schema version "
        f"{contract['schema_version']}: **{contract['tool_count']} tools** behind "
        f"**{contract['capability_count']} capabilities**."
    )
    lines.append("")
    lines.append("| Tool | Kind | Reads | Scopes | Timeout |")
    lines.append("|---|---|---|---|---|")
    for tool in tools:
        lines.append(
            f"| `{tool['name']}` | {tool['kind']} | {tool['source']} "
            f"| {scope_expression(tool['discovery_scope_sets'])} "
            f"| {tool['timeout_ms']} ms |"
        )

    for tool in tools:
        # A write tool has no resources -- it is one-to-one with its operation
        # (D470) -- so without its own detail section it would render as a bare
        # table row, and the numbers a reader acts on (the side-effect bound,
        # the argument names, what the audit record will not carry) would exist
        # only in the contract JSON.
        if tool["kind"] == "write":
            lines.append("")
            lines.append(f"### `{tool['name']}`")
            lines.append("")
            effect = "idempotent" if tool["idempotent"] else "not idempotent"
            lines.append(
                f"**Write** — operation `{tool['operation']['operation_id']}`, at most "
                f"**{tool['max_affected_rows']}** affected rows, {effect}, requires "
                f"{scope_expression([list(tool['required_scopes'])])}."
            )
            lines.append("")
            lines.append(
                "- Arguments, by name and in order: "
                + ", ".join(f"`{argument}`" for argument in tool["arguments"])
            )
            redacted = tool.get("audit_redact") or []
            if redacted:
                lines.append(
                    "- Redacted from the audit record: "
                    + ", ".join(f"`{parameter}`" for parameter in redacted)
                )
            else:
                lines.append("- Redacted from the audit record: nothing")
            continue
        resources = sorted(tool.get("resources", []), key=lambda entry: entry["name"])
        if not resources:
            continue
        lines.append("")
        lines.append(f"### `{tool['name']}`")
        for resource in resources:
            lines.append("")
            lines.append(
                f"**`{resource['name']}`** — capability `{resource['capability']}`, "
                f"at most **{resource['max_rows']}** rows, requires "
                f"{scope_expression([list(resource['required_scopes'])])}."
            )
            lines.append("")
            lines.append("- Columns: " + ", ".join(f"`{column}`" for column in resource["columns"]))
            filters = resource.get("filters") or []
            if isinstance(filters, dict):
                pairs = sorted(filters.items())
            else:
                pairs = sorted((entry["column"], entry["operators"]) for entry in filters)
            if pairs:
                rendered = "; ".join(
                    f"`{column}` ({', '.join(sorted(operators))})" for column, operators in pairs
                )
                lines.append(f"- Filters: {rendered}")
            else:
                lines.append("- Filters: none")
            ordering = resource.get("order_by") or []
            if ordering:
                rendered = ", ".join(
                    f"`{entry['column']}` {entry['direction']}" for entry in ordering
                )
                lines.append(f"- Orderings, chosen by INDEX rather than written: {rendered}")
            else:
                lines.append("- Orderings: none")

    return "\n".join(lines)


def shown(path: Path) -> str:
    """A path to put in a message, repository-relative where that makes sense.

    `relative_to` RAISES for a path outside the repository, and this function is
    only ever called from a failure branch -- so the bare version turned "the
    catalog has drifted" into a `ValueError` with a traceback, which is a
    diagnostic that hides the thing it was written to report.

    Found by the test that perturbs the catalog to check that `--check` can fail
    at all. The guard-the-guard arm found a defect in the guard.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def compose(existing: str, generated: str) -> str:
    if BEGIN not in existing or END not in existing:
        raise SystemExit(f"{CATALOG} has no generated block. It must contain {BEGIN} and {END}.")
    head = existing[: existing.index(BEGIN) + len(BEGIN)]
    tail = existing[existing.index(END) :]
    return f"{head}\n\n{generated}\n\n{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the catalog")
    group.add_argument("--check", action="store_true", help="report drift; never write")
    arguments = parser.parse_args()

    generated = render(load_contract())
    existing = CATALOG.read_text(encoding="utf-8")
    wanted = compose(existing, generated)

    if arguments.check:
        if wanted != existing:
            print(
                f"render-mcp-catalog: {shown(CATALOG)} has drifted from "
                f"{shown(CONTRACT)}. Run bin/render-mcp-catalog.py --write.",
                file=sys.stderr,
            )
            return 5
        print(f"render-mcp-catalog: {shown(CATALOG)} is current")
        return 0

    if wanted != existing:
        CATALOG.write_text(wanted, encoding="utf-8")
        print(f"render-mcp-catalog: updated {shown(CATALOG)}")
    else:
        print(f"render-mcp-catalog: {shown(CATALOG)} was already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
