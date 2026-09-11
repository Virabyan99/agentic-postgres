#!/usr/bin/env python
"""Scaffold one capability entry for a project's own agent surface (ADR 0201).

``init --project FILE --operation NAME [--relation NAME] [--kind read|write]``
streams **one capability entry** to standard output, derived from the merged
reviewed surface (release + project, ADR 0198) -- the same operations table
the compiler resolves against, which is why this scaffold cannot express what
the compiler cannot emit (D1137). It writes no file: the redirect happens in
the caller's own shell, so an entry lands where a human has to read it before
it is reviewed.

* a **relation** scaffolds a read grouped under the release's `query_resource`:
  the view's column list, no filters, no orderings, `max_rows` 100, `risk: low`,
  scope `<relation>:read`;
* an **RPC** scaffolds a write: the reviewed argument list in PostgreSQL order,
  `supports_dry_run: true`, `requires_approval: true`, `idempotent: false`,
  every argument redacted, `risk: moderate`, and the scope of the relation the
  REVIEWER names with `--relation` -- a write's scope is a review decision, so
  the scaffold takes it as an argument and never guesses it.

``init --head`` prints the fixed head of a project's manifest (the YAML
language server's schema line, D1138; `schema_version: 4`; `capabilities:`),
so a manifest is `init --head`, then one `init --operation` per entry.

Every budget is the conservative end of a bound a profile could narrow (ADR
0183's polarity, D925). An operation the merged surface does not name is
refused with the ones it does; an operation in `agent_rpcs` is refused as the
platform's (ADR 0201); `--kind` may only confirm the kind the object derives.

Where the other verbs live, rather than wrapped here (D707):
  validate   bin/mcp-contract.sh check --project FILE
  test       bin/render-evaluation-report.py --check --project FILE
  dry-run    the runtime's own, per call (ADR 0182)

Exit codes (runbook section 2 convention):
  0  success
  2  invalid operator input, including an operation the surface does not name
  3  missing local prerequisite: a manifest without a set, or a set without
     its reviewed surface
  5  a manifest or surface that does not load
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, api_surface, capability_compiler, config

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_CONTRACT = 5

#: The fixed head of a project's capability manifest. The first line is the
#: YAML language server's modeline (D1138): an editor that embeds that server
#: validates the file's SHAPE against the schema as it is typed; approval
#: against the reviewed surface is `mcp-contract.sh check --project`'s.
MANIFEST_HEAD = """\
# yaml-language-server: $schema=../../schemas/capabilities.schema.json
#
# This project's own capability manifest (ADR 0201): the tools an agent may
# call over this project's tables, beside the migration set that creates them.
# Each entry below was written by `bin/agent.sh init`, then reviewed; it is
# compiled against the MERGED reviewed surface and this project's snapshot by
# `bin/mcp-contract.sh compile --project <manifest>` into
# contracts/mcp-capabilities.canonical.json, and `check --project` refuses a
# manifest that no longer compiles to the committed contract.
#
# A project may also leave release capabilities out of ITS lock:
#
#   release:
#     disabled: [create_note]
#
# What a project may not declare is refused by name: a metadata capability,
# an agent-plane operation, a read over an RPC with arguments, a name the
# release already serves.
schema_version: 4
capabilities:
"""

READ_MAX_ROWS = 100
READ_MAX_RESPONSE_BYTES = 262144
WRITE_MAX_RESPONSE_BYTES = 65536
TIMEOUT_MS = 5000


class ScaffoldError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def fail(code: int, message: str) -> int:
    print(f"agent: {message}", file=sys.stderr)
    return code


def merged_surface_for(project_path: Path) -> dict[str, Any]:
    """The merged reviewed surface a project's capabilities are approved against."""
    if not project_path.is_file():
        raise ScaffoldError(EXIT_PREREQUISITE, f"project manifest not found: {project_path}")
    manifest = config.load_project_manifest(project_path)
    named = config.project_migration_set(manifest)
    if named is None:
        raise ScaffoldError(
            EXIT_PREREQUISITE,
            f"{project_path} declares no migrations.set, so there is no merged surface to "
            "scaffold from. A project's capabilities are over its own reviewed surface, "
            "which lives beside its migration set (ADR 0198, ADR 0201).",
        )
    surface_path = api_surface.project_contract_path(REPO_ROOT / named)
    if not surface_path.is_file():
        raise ScaffoldError(
            EXIT_PREREQUISITE,
            f"{named} has no reviewed surface at {surface_path.relative_to(REPO_ROOT)}; write "
            "it first and check it with `bin/api-contract.sh --check --project <manifest>`.",
        )
    project = api_surface.load_project_surface(surface_path)
    return api_surface.merged_surface(api_surface.load_surface(), project)


def flow(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


def read_entry(name: str, columns: list[str]) -> str:
    return f"""\
  - name: query_{name}
    tool: query_resource
    description: >-
      The caller's own rows of {name}, filtered and ordered within frozen
      bounds. Scaffolded by `bin/agent.sh init`; add the filters and orderings
      a caller may use, and nothing the view does not publish.
    kind: read
    version: 1.0.0
    lifecycle: active
    risk: low
    max_response_bytes: {READ_MAX_RESPONSE_BYTES}
    max_concurrent_calls: 1
    enabled: true
    required_scopes: [{name}:read]
    operation:
      source: postgrest
      operation_id: {name}.get
    resource: {name}
    columns: {flow(columns)}
    filters: []
    order_by: []
    max_rows: {READ_MAX_ROWS}
    timeout_ms: {TIMEOUT_MS}
    audit:
      redact: []
"""


def write_entry(name: str, arguments: list[str], relation: str) -> str:
    return f"""\
  - name: {name}
    description: >-
      One reviewed write, {name}, over the caller's own rows. Scaffolded by
      `bin/agent.sh init` at the conservative end of every bound: a rehearsal
      is supported, approval is required, every argument is redacted.
    kind: write
    version: 1.0.0
    lifecycle: active
    risk: moderate
    max_response_bytes: {WRITE_MAX_RESPONSE_BYTES}
    max_concurrent_calls: 1
    supports_dry_run: true
    requires_approval: true
    enabled: true
    required_scopes: [{relation}:write]
    operation:
      source: postgrest
      operation_id: rpc.{name}.post
    max_affected_rows: 1
    idempotent: false
    timeout_ms: {TIMEOUT_MS}
    audit:
      redact: {flow(arguments)}
"""


def scaffold(
    surface: dict[str, Any], operation: str, *, kind: str | None, relation: str | None
) -> str:
    """One entry, or a refusal that names what the surface does name."""
    operations = capability_compiler.surface_operations(surface)
    publishable = sorted(
        {
            entry["name"]
            for entry in operations.values()
            if entry["section"] in {"relations", "rpcs"}
        }
    )
    matches = [entry for entry in operations.values() if entry["name"] == operation]
    if not matches:
        raise ScaffoldError(
            EXIT_INPUT,
            f"the merged reviewed surface names no operation {operation!r}. It names: "
            f"{', '.join(publishable)}. An object the surface does not publish cannot be "
            "given to an agent (ADR 0050); publish it in the project's reviewed surface first.",
        )
    section = matches[0]["section"]
    release = api_surface.load_surface()
    if operation in release["relations"] or operation in release["rpcs"]:
        raise ScaffoldError(
            EXIT_INPUT,
            f"{operation!r} is the release's own object, and the release's capabilities over "
            "it are already reviewed and compiled. A project narrows one with mcp.profile "
            "(ADR 0183) or leaves it out of its lock with release.disabled (ADR 0201); a "
            "second capability over it would be refused at the join as a name the release "
            "already serves.",
        )
    if section == "agent_rpcs":
        raise ScaffoldError(
            EXIT_INPUT,
            f"{operation!r} is an agent-plane operation and the platform's; a project's tool "
            "addresses only what the reviewed surface publishes (ADR 0201). It names: "
            f"{', '.join(publishable)}.",
        )

    derived = "read" if section == "relations" else "write"
    if kind is not None and kind != derived:
        raise ScaffoldError(
            EXIT_INPUT,
            f"{operation!r} is a {'relation' if derived == 'read' else 'reviewed RPC'}, which "
            f"scaffolds a {derived}; --kind {kind} does not apply. A read over an RPC has one "
            "shape, an argument-free RPC (ADR 0200), and is written by hand from the "
            "release's `run_report`.",
        )

    if derived == "read":
        if relation is not None:
            raise ScaffoldError(
                EXIT_INPUT,
                f"--relation does not apply to a relation: {operation!r}'s read scope is "
                f"{operation}:read by derivation (ADR 0200).",
            )
        return read_entry(operation, list(surface["relations"][operation]["columns"]))

    if relation is None:
        raise ScaffoldError(
            EXIT_INPUT,
            f"{operation!r} is a write, and a write's scope is a review decision: name the "
            "relation it writes with --relation NAME, and the entry requires <NAME>:write. "
            f"The merged surface publishes: {', '.join(sorted(surface['relations']))}.",
        )
    if relation not in surface["relations"]:
        raise ScaffoldError(
            EXIT_INPUT,
            f"--relation {relation!r} is not a relation the merged surface publishes "
            f"({', '.join(sorted(surface['relations']))}), so {relation}:write is not a scope "
            "the compiler would approve (ADR 0200).",
        )
    return write_entry(operation, list(matches[0]["arguments"]), relation)


def command_init(arguments: argparse.Namespace) -> int:
    if arguments.head:
        if arguments.operation or arguments.relation or arguments.kind:
            return fail(
                EXIT_INPUT, "--head prints the manifest's fixed head and takes no operation"
            )
        sys.stdout.write(MANIFEST_HEAD)
        return EXIT_OK
    if arguments.project is None or arguments.operation is None:
        return fail(EXIT_INPUT, "init needs --project FILE and --operation NAME (or --head)")
    try:
        surface = merged_surface_for(arguments.project)
        entry = scaffold(
            surface, arguments.operation, kind=arguments.kind, relation=arguments.relation
        )
    except ScaffoldError as error:
        return fail(error.code, str(error))
    except config.ManifestError as error:
        return fail(EXIT_CONTRACT, str(error))
    sys.stdout.write(entry)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="scaffold one capability entry to stdout")
    init.add_argument("--project", type=Path, default=None, help="the project manifest")
    init.add_argument(
        "--operation", default=None, help="a relation or RPC the merged surface names"
    )
    init.add_argument("--kind", choices=("read", "write"), default=None, help="confirms the kind")
    init.add_argument(
        "--relation", default=None, help="for a write: the relation whose write scope it takes"
    )
    init.add_argument("--head", action="store_true", help="print the manifest's fixed head")
    arguments = parser.parse_args(argv)
    return {"init": command_init}[arguments.command](arguments)


if __name__ == "__main__":
    raise SystemExit(main())
