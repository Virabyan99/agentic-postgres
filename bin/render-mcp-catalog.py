#!/usr/bin/env python
"""Generate the MCP tool catalog from the committed capability contract.

The catalog is what a person reads to find out what this deployment's agent
surface offers: every tool the contract carries, the scopes each needs, and for
the read tools the frozen columns, filters and orderings behind them. It is
derived from
``contracts/snapshots/mcp/mcp-capabilities.canonical.json`` -- the compiled,
project-neutral contract ``bin/mcp-contract.sh`` produces and checks -- for the
reason ``render-acceptance-matrix.py`` derives its tables from the registry: a
hand-maintained copy drifts, and the failure mode is silent. A catalog listing a
tool the contract does not carry, or omitting a filter it does, is a document
that tells a reader the surface is something other than what it is.

**A project's own tools are catalogued the same way** (ADR 0201, D1309).
``--project FILE`` names a project manifest that declares ``mcp.capabilities``,
and the catalog rendered is ``projects/<slug>/docs/mcp-tool-catalog.md``, from
that project's committed contract beside its reviewed surface. What it lists is
the project's OWN tools and **not the whole of what its deployment serves** --
the deploy joins them with the release's into one lock (ADR 0201) -- so the
generated block says that in its first lines, names where the release's rows
are, and marks any tool name both contracts carry. Two authorizations under one
name is the thing a reader granting a scope has to get right, which is D421 one
level up: `query_resource` over a project's view and `query_resource` over the
release's are different grants.

The file is **created** by ``--write --project`` when it is absent, the way
``render-evaluation-report.py`` creates a project's report. A first catalog has
nowhere to come from, and reading an absent file to find its markers is a
traceback rather than a report (D1325, ADR 0195).

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
    2  invalid operator input
    5  generated documentation has drifted
"""

from __future__ import annotations

import argparse
import os.path
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, capability_manifest, config

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
CATALOG = REPO_ROOT / "docs" / "mcp-tool-catalog.md"

#: Where a project's catalog goes, relative to `projects/<slug>`.
#:
#: `docs/` rather than beside the contract: the compiled contract is an input
#: this renderer reads and a document is what it writes, and a reader looking
#: for a project's reference material has one place to look.
PROJECT_CATALOG = Path("docs") / "mcp-tool-catalog.md"

BEGIN = "<!-- BEGIN GENERATED: mcp-catalog -->"
END = "<!-- END GENERATED: mcp-catalog -->"

#: What a project's catalog holds AROUND its generated block when this command
#: creates it. Short on purpose: the release's catalog explains what a tool is,
#: and a project's is an inventory of its own.
PROJECT_CATALOG_HEAD = """# The agent tool catalog for this project

What THIS project's own agent surface offers: the tools its capability manifest
declares, compiled from its reviewed surface and committed beside it.

**The block below is generated** by `bin/render-mcp-catalog.py --project
<manifest>`. Regenerate rather than edit; `--check --project` catches a drift
and exits 5 (ADR 0201, D1309).

"""

#: Write-tool parameters the RUNTIME requires and the contract does not carry.
#:
#: **A second copy of `mcp_tools.RESERVED_WRITE_PARAMETERS`, with a contract test
#: between them** (D486's pattern, ADR 0181). This script runs from the
#: repository root and imports no service package; importing one to avoid a
#: duplicate would trade a compared pair for a fragile path, and a test that
#: compares a value with itself is the shape §6 warns about.
RESERVED_WRITE_PARAMETERS = ("idempotency_key", "dry_run")


def load_contract(path: Path = CONTRACT) -> dict[str, Any]:
    """Read a compiled contract; an unreadable one is reported, not raised.

    The parse lives in `capability_manifest` because three other commands read
    the same kind of file and all four met an empty one as a traceback (D1359).
    """
    return capability_manifest.load_contract_document(path)


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
    # **The risk column exists only at contract schema version 2** (ADR 0177),
    # and its absence at v1 is deliberate rather than a rendering convenience. A
    # column reading "—" on every row would say this deployment classifies its
    # capabilities and declined to, which is the reverse of the truth: a v1
    # contract does not carry the field at all (D600).
    versioned = contract["schema_version"] >= 2
    lines.append(
        "| Tool | Kind | Reads | Scopes | Timeout | Risk |"
        if versioned
        else "| Tool | Kind | Reads | Scopes | Timeout |"
    )
    lines.append("|---|---|---|---|---|---|" if versioned else "|---|---|---|---|---|")
    for tool in tools:
        row = (
            f"| `{tool['name']}` | {tool['kind']} | {tool['source']} "
            f"| {scope_expression(tool['discovery_scope_sets'])} "
            f"| {tool['timeout_ms']} ms |"
        )
        lines.append(row + f" {tool['risk']} |" if versioned else row)

    if versioned:
        lines.append("")
        lines.append(
            "Each tool's backing capabilities, with the version and lifecycle each "
            "declares. **A tool has no single version of its own**: `query_resource` "
            "is two authorizations behind one name (ADR 0120) and they move "
            "independently, so the list is the authority and the tool-level risk "
            "above is the only aggregate."
        )
        lines.append("")
        lines.append("| Tool | Capability | Version | Lifecycle | Risk |")
        lines.append("|---|---|---|---|---|")
        for tool in tools:
            for capability in tool["capabilities"]:
                lines.append(
                    f"| `{tool['name']}` | `{capability['name']}` "
                    f"| {capability['version']} | {capability['lifecycle']} "
                    f"| {capability['risk']} |"
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
            # The runtime's own parameters, which the CONTRACT does not carry
            # because they are not the database function's (ADR 0181). Published
            # anyway: this document says what an agent can do against this
            # deployment, and a REQUIRED parameter it does not mention makes the
            # document wrong in the direction a reader cannot detect.
            lines.append(
                "- Also required by the tool, and not part of the operation: "
                + ", ".join(f"`{parameter}`" for parameter in RESERVED_WRITE_PARAMETERS)
                + " — the caller's own token for this operation. Send the same one to "
                "retry safely; the same key with different arguments is refused rather "
                "than deduplicated."
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


def compose(existing: str, generated: str, catalog: Path = CATALOG) -> str:
    if BEGIN not in existing or END not in existing:
        raise SystemExit(f"{catalog} has no generated block. It must contain {BEGIN} and {END}.")
    head = existing[: existing.index(BEGIN) + len(BEGIN)]
    tail = existing[existing.index(END) :]
    return f"{head}\n\n{generated}\n\n{tail}"


@dataclass(frozen=True)
class Target:
    """One catalog: which contract it is rendered from, and which file it is."""

    catalog: Path
    contract: dict[str, Any]
    contract_path: Path
    #: `projects/<slug>`'s slug, or None for the release's own catalog.
    slug: str | None


def release_target() -> Target:
    return Target(
        catalog=CATALOG,
        contract=load_contract(CONTRACT),
        contract_path=CONTRACT,
        slug=None,
    )


def project_target(project_path: Path) -> Target:
    """The catalog for the project a manifest names.

    The contract is READ, not compiled. `bin/mcp-contract.sh check --project`
    is what proves the committed file is current, and a renderer that compiled
    its own input would be a second authority for what the project publishes --
    which is the shape ADR 0002 refuses and the reason this file derives the
    release's catalog from the committed snapshot rather than from
    `capabilities.example.yaml`.
    """
    manifest = config.load_project_manifest(project_path)
    named = config.project_capabilities(manifest)
    if named is None:
        raise config.ManifestError(
            f"{project_path} declares no mcp.capabilities, so it has no agent surface of "
            "its own to catalog; without --project this renders the release's"
        )
    root = REPO_ROOT / named
    contract_path = capability_manifest.project_contract_path(root)
    if not contract_path.is_file():
        raise config.ManifestError(
            f"{shown(contract_path)} does not exist, so there is nothing to render. "
            f"Compile it first: bin/mcp-contract.sh compile --project {project_path} > "
            f"{shown(contract_path)}"
        )
    return Target(
        catalog=root / PROJECT_CATALOG,
        contract=load_contract(contract_path),
        contract_path=contract_path,
        slug=root.name,
    )


def project_header(target: Target, release: dict[str, Any]) -> str:
    """The lines a project's block opens with, derived rather than written.

    **What it is for.** A catalog that listed a project's two tools under the
    same heading the release's six use would tell a reader their deployment
    serves two, which is the failure mode this whole file exists to prevent one
    level up. So the block names the project, says what it is not, and points
    at the other half.

    **The shared names are read out of the release contract**, not listed here.
    `query_resource` is one name over two contracts today; which names those are
    is a fact about two files, and a copy of it here would be the drift a
    generated document is written to avoid.
    """
    assert target.slug is not None
    release_names = {tool["name"] for tool in release["tools"]}
    shared = sorted(
        tool["name"] for tool in target.contract["tools"] if tool["name"] in release_names
    )
    link = os.path.relpath(CATALOG, target.catalog.parent)

    lines = [
        f"Project `{target.slug}`, from `{shown(target.contract_path)}`.",
        "",
        "**These are this project's own tools, and not the whole of what its deployment "
        f"serves.** The release's are in [the release catalog]({link}); a deploy compiles "
        "both into one lock (ADR 0201) and the deployed document publishes that lock's "
        "digest as `capability_contract_sha256`.",
    ]
    if shared:
        names = ", ".join(f"`{name}`" for name in shared)
        verb = "is a tool name" if len(shared) == 1 else "are tool names"
        lines += [
            "",
            f"{names} {verb} the release serves too, over its own relations. The two are "
            "different authorizations under one name: a scope granted for one grants "
            "nothing for the other, and the lock carries both.",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the catalog")
    group.add_argument("--check", action="store_true", help="report drift; never write")
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        metavar="FILE",
        help="a project manifest naming mcp.capabilities; renders THAT project's catalog "
        "at projects/<slug>/docs/mcp-tool-catalog.md from its committed contract (ADR 0201)",
    )
    arguments = parser.parse_args()

    try:
        target = (
            release_target() if arguments.project is None else project_target(arguments.project)
        )
    except config.CapabilityContractError as error:
        # **A contract that is there and cannot be read is a CONTRACT failure**
        # (D1359), not invalid operator input: nothing the operator typed is
        # wrong, and the file the documented redirect left behind is the cause.
        print(f"render-mcp-catalog: {error}", file=sys.stderr)
        return 5
    except config.ManifestError as error:
        print(f"render-mcp-catalog: {error}", file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print(f"render-mcp-catalog: missing input: {error}", file=sys.stderr)
        return 2

    generated = render(target.contract)
    if target.slug is not None:
        generated = f"{project_header(target, load_contract(CONTRACT))}\n\n{generated}"

    catalog = target.catalog
    if catalog.is_file():
        existing = catalog.read_text(encoding="utf-8")
    elif target.slug is not None:
        existing = f"{PROJECT_CATALOG_HEAD}{BEGIN}\n{END}\n"
    else:
        raise SystemExit(f"{catalog} does not exist")
    wanted = compose(existing, generated, catalog)
    suffix = "" if arguments.project is None else f" --project {arguments.project}"

    if arguments.check:
        if not catalog.is_file():
            print(
                f"render-mcp-catalog: {shown(catalog)} does not exist. Run "
                f"bin/render-mcp-catalog.py --write{suffix}.",
                file=sys.stderr,
            )
            return 5
        if wanted != existing:
            print(
                f"render-mcp-catalog: {shown(catalog)} has drifted from "
                f"{shown(target.contract_path)}. Run bin/render-mcp-catalog.py --write"
                f"{suffix}.",
                file=sys.stderr,
            )
            return 5
        print(f"render-mcp-catalog: {shown(catalog)} is current")
        return 0

    if not catalog.is_file() or wanted != existing:
        catalog.parent.mkdir(parents=True, exist_ok=True)
        catalog.write_text(wanted, encoding="utf-8")
        print(f"render-mcp-catalog: updated {shown(catalog)}")
    else:
        print(f"render-mcp-catalog: {shown(catalog)} was already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
