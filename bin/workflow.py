#!/usr/bin/env python3
"""The work behind `bin/workflow.sh` (ADR 0228, ADR 0229).

Two verbs are answered here in this checkout -- `init` and `validate` -- and
both are pure reads of a project manifest, its lock and its own files. Neither
reaches a host, a root or a render.

The other four (`run`, `dry-run`, `status`, `cancel`) call the auth service's
workflow routes. They are DECLARED here, with real help, and they refuse with
exit 3 until Session 32 Run 5 builds the routes: a verb that is documented and
silently missing is worse than one that says which release serves it.

This command imports `agentic_postgres` and `yaml` and nothing else (ADR 0093).
It holds no SQL, no token and no route.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import REPO_ROOT, config, workflow_definition

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5

#: The verbs that reach the deployment. Run 5 replaces this with the routes.
HTTP_VERBS = ("run", "dry-run", "status", "cancel")

#: What a verb this checkout does not serve says. One sentence, naming the run
#: that serves it, so an operator reading it knows whether to upgrade or to
#: stop looking for a flag they got wrong.
NOT_YET = (
    "{verb} is not yet available in this checkout (Session 32 Run 5). "
    "The definition half -- init and validate -- is complete, and a definition "
    "this checkout validates is installed by a deploy at step 6d."
)

DEFAULT_SKELETON_NAME = "example-workflow"

#: `app_private.workflow_definition.name`'s own CHECK, restated so `init`
#: refuses a name the deploy would refuse rather than scaffolding one.
DEFINITION_NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")


def fail(code: int, message: str) -> None:
    print(f"workflow: {message}", file=sys.stderr)
    raise SystemExit(code)


def _manifest(path: Path) -> dict:
    try:
        return config.load_project_manifest(path)
    except config.ManifestError as error:
        fail(EXIT_REFUSED, f"cannot read the project manifest: {error}")
    except FileNotFoundError as error:
        fail(EXIT_PREREQUISITE, f"missing input: {error}")
    raise AssertionError("unreachable")


def _lock(arguments: argparse.Namespace) -> workflow_definition.LockView:
    try:
        return workflow_definition.lock_view_for_project(
            Path(arguments.project), arguments.capabilities
        )
    except config.ManifestError as error:
        fail(EXIT_REFUSED, f"the project's lock does not compile: {error}")
    except config.CapabilityContractError as error:
        fail(EXIT_REFUSED, str(error))
    except FileNotFoundError as error:
        fail(EXIT_PREREQUISITE, f"missing input: {error}")
    raise AssertionError("unreachable")


def _project_set_root(document: dict) -> Path | None:
    """`projects/<slug>`, from `migrations.set`, or None when there is none.

    From the migration set and not from `mcp.capabilities`: the workflows live
    beside the migrations, and a project can declare a set without declaring
    capabilities of its own.
    """
    named = config.project_migration_set(document)
    return None if named is None else REPO_ROOT / named


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

SKELETON = """\
# A workflow definition for {key}, scaffolded from its compiled lock.
#
# Read it before it is reviewed. Every capability named below is one this
# project's lock really serves at the version shown, so this compiles as it
# stands -- but the arguments are placeholders and the names say nothing about
# what the workflow is FOR, which is the part a scaffold cannot write.
#
# Install it by putting it in {directory}/ and deploying: step 6d compiles
# every definition there and installs it. A (name, version) already installed
# with a different source refuses the deploy.
---
schema_version: 1
name: {name}
version: 1
description: >-
  TODO: what this workflow is for, in a sentence a reviewer can check the
  steps against.
timeout_seconds: 600

steps:
{steps}"""

READ_STEP = """\
  - name: read_something
    capability: {capability}
    arguments:
      limit: 5
"""

RPC_READ_STEP = """\
  - name: read_something
    capability: {capability}
    # An RPC read takes no arguments: the lock names the operation and the
    # caller chooses nothing about it.
"""

WRITE_STEP = """\
  - name: write_something
    capability: {capability}
    arguments:
{argument_lines}\
"""


def _first_read(lock: workflow_definition.LockView) -> tuple[str, str] | None:
    """The first read capability the lock serves, with its tool's shape."""
    for tool in sorted(lock.tools, key=lambda item: item.name):
        if tool.kind != "read":
            continue
        for capability in sorted(tool.capabilities, key=lambda item: item.name):
            if capability.lifecycle == workflow_definition.ACTIVE:
                return f"{capability.name}@{capability.version}", tool.read_shape or "relation"
    return None


def _first_write(
    lock: workflow_definition.LockView,
) -> tuple[str, tuple[str, ...]] | None:
    """The first write that does NOT require approval, with its arguments.

    Approval-requiring writes are skipped rather than scaffolded and commented
    out: the compiler refuses them until Session 33, and a scaffold whose first
    suggestion does not compile is a scaffold that teaches the wrong thing.
    """
    for tool in sorted(lock.tools, key=lambda item: item.name):
        if tool.kind != "write":
            continue
        for capability in sorted(tool.capabilities, key=lambda item: item.name):
            if capability.lifecycle != workflow_definition.ACTIVE:
                continue
            if capability.requires_approval:
                continue
            return f"{capability.name}@{capability.version}", tool.arguments
    return None


def command_init(arguments: argparse.Namespace) -> int:
    document = _manifest(Path(arguments.project))
    lock = _lock(arguments)

    name = arguments.name or DEFAULT_SKELETON_NAME
    if not DEFINITION_NAME.fullmatch(name):
        fail(
            EXIT_INPUT,
            f"{name!r} is not a definition name; the column's own constraint is "
            "^[a-z][a-z0-9-]{0,62}$",
        )

    read = _first_read(lock)
    write = _first_write(lock)
    if read is None and write is None:
        fail(
            EXIT_REFUSED,
            "this project's lock serves no active read and no approval-free write, so "
            "there is no step a scaffold could name. A workflow over it would have "
            "nothing to do.",
        )

    steps = ""
    if read is not None:
        capability, shape = read
        template = READ_STEP if shape == "relation" else RPC_READ_STEP
        steps += template.format(capability=capability)
    if write is not None:
        capability, names = write
        argument_lines = "".join(f"      {argument}: TODO\n" for argument in names)
        steps += WRITE_STEP.format(capability=capability, argument_lines=argument_lines)

    root = _project_set_root(document)
    directory = (
        f"{root.relative_to(REPO_ROOT)}/{workflow_definition.WORKFLOWS_SUBDIR}"
        if root is not None
        else f"projects/<slug>/{workflow_definition.WORKFLOWS_SUBDIR}"
    )
    print(
        SKELETON.format(
            key=document["project"]["slug"] + "-" + document["project"]["environment"],
            directory=directory,
            name=name,
            steps=steps,
        ),
        end="",
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def command_validate(arguments: argparse.Namespace) -> int:
    document = _manifest(Path(arguments.project))

    if arguments.file is not None:
        paths = [Path(arguments.file)]
    else:
        root = _project_set_root(document)
        if root is None:
            print(
                "workflow: this project declares no migrations.set, so it has no "
                "workflows/ directory of its own and there is nothing to validate."
            )
            return EXIT_OK
        paths = workflow_definition.definitions_of(root)
        if not paths:
            print(
                f"workflow: {root.relative_to(REPO_ROOT)}/"
                f"{workflow_definition.WORKFLOWS_SUBDIR}/ holds no definitions; this "
                "project declares none."
            )
            return EXIT_OK

    lock = _lock(arguments)

    # **Held until every file has compiled** (D1403). A per-file success line
    # printed as it went would put "compiles" on the terminal above a refusal,
    # and a sentence already on the terminal cannot be taken back.
    report: list[str] = []
    for path in paths:
        try:
            compiled = workflow_definition.compile_file(path, lock)
        except workflow_definition.DefinitionError as error:
            where = (
                f"step {error.step_name}: {error.reason}"
                if error.step_name is not None
                else error.reason
            )
            fail(EXIT_REFUSED, f"{path}: {where}")
        report.append(
            f"  {path.name:<28} {compiled.name} v{compiled.version}  "
            f"{len(compiled.steps)} steps  scopes: "
            f"{', '.join(compiled.required_scopes) or 'none'}"
        )

    print(f"workflow: {len(paths)} definition(s) compile against this project's lock")
    print("\n".join(report))
    print(f"  lock tools_sha256  {lock.tools_sha256}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# the four that reach a deployment
# ---------------------------------------------------------------------------


def command_not_yet(arguments: argparse.Namespace) -> int:
    fail(EXIT_PREREQUISITE, NOT_YET.format(verb=arguments.command))
    raise AssertionError("unreachable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bin/workflow.sh", add_help=False)
    parser.add_argument("command", choices=("init", "validate", *HTTP_VERBS))
    parser.add_argument("--project", default=None)
    parser.add_argument("--project-outputs", dest="project_outputs", default=None)
    parser.add_argument("--capabilities", type=Path, default=None)
    parser.add_argument("--file", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--input", dest="input_document", default=None)
    parser.add_argument("--definition-version", dest="definition_version", default=None)
    parser.add_argument("--subject", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.command in HTTP_VERBS:
        return command_not_yet(arguments)

    if arguments.project is None:
        fail(EXIT_INPUT, f"{arguments.command} requires --project FILE")
    if not Path(arguments.project).is_file():
        fail(EXIT_INPUT, f"--project names no file: {arguments.project}")

    if arguments.command == "init":
        return command_init(arguments)
    return command_validate(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
