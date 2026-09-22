#!/usr/bin/env python3
"""The work behind `bin/workflow.sh` (ADR 0228, ADR 0229).

Two verbs are pure reads of a project manifest, its lock and its own files:
`init` and `validate` reach no host, no root and no render.

The other four call the auth service's three workflow routes. They hold no SQL,
no route that `ROUTES` does not enumerate, and **no token**: the credential
comes from `APG_AGENT_TOKEN` in this process's environment and is never an
argument, because an argument is a value `ps` can read (D105, D1160). That is
`bin/api.sh`'s shape, and the reason is the same.

This command imports `agentic_postgres` and `yaml` and nothing else (ADR 0093).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import REPO_ROOT, config, workflow_definition

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5

#: The verbs that reach the deployment.
HTTP_VERBS = ("run", "dry-run", "status", "cancel")

#: **The closed table** (ADR 0093's spirit, `bin/api.py`'s `OPERATIONS`). Four
#: verbs over THREE routes -- `dry-run` is `run` with a flag, not a fourth
#: address -- and a path this table does not name is a path this command
#: cannot reach. A proof reads it and refuses any other URL construction in the
#: module.
ROUTES: dict[str, tuple[str, str]] = {
    "run": ("POST", "/workflows/runs"),
    "status": ("GET", "/workflows/runs/{run_id}"),
    "cancel": ("POST", "/workflows/runs/{run_id}/cancel"),
}

#: Where the token comes from, and it is never an argument.
#:
#: (S105 matches on the NAME. This is the name of an environment variable, not
#: a credential; `bin/api.py:31` carries the same comment for the same reason.)
TOKEN_VARIABLE = "APG_AGENT_TOKEN"  # noqa: S105

REQUEST_TIMEOUT_SECONDS = 30

DEFAULT_SKELETON_NAME = "example-workflow"

#: `name@version`, the spelling a step uses for a capability. One string rather
#: than two flags, because a definition is identified by the pair and a caller
#: that could give one without the other would be a caller that could ask for
#: "the latest", which no table in this product has.
DEFINITION_REFERENCE = re.compile(r"^([a-z][a-z0-9-]{0,62})@([0-9]+)$")

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


def _app_base(path: Path) -> str:
    """The deployment's app route, read from a rendered outputs document.

    Read, never derived. `outputs.json` is the one place every derived identity
    is published (ADR 0002), and a command that rebuilt the URL would be a
    second derivation of an address `naming` owns.
    """
    if not path.is_file():
        fail(EXIT_INPUT, f"outputs document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(EXIT_INPUT, f"cannot read {path}: {error}")

    route = (document.get("routes") or {}).get("app")
    url = route.get("url") if isinstance(route, dict) else route
    if not isinstance(url, str) or not url:
        fail(
            EXIT_REFUSED,
            "this document publishes no app route. A project deployed through a "
            "session before 6 is in that state, and so is one whose deploy has not "
            "observed its routes yet.",
        )
    if urlsplit(url).scheme not in ("https", "http"):
        fail(EXIT_REFUSED, f"routes.app is not a URL: {url!r}")
    return url.rstrip("/")


def _token() -> str:
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        fail(
            EXIT_PREREQUISITE,
            f"{TOKEN_VARIABLE} is empty. A run is started AS AN AGENT, so this command "
            "needs an agent token in its environment -- and never as an argument, "
            "because an argument is a value `ps` can read. Mint one with "
            "`bin/api.sh`'s sibling flow: POST /auth/agent-token with the agent's id "
            "and the secret it was shown once.",
        )
    return token


def _call(
    base: str, verb: str, *, run_id: str | None = None, body: dict[str, Any] | None = None
) -> tuple[int, str]:
    """One request against ONE of the three enumerated routes."""
    method, template = ROUTES[verb]
    path = template.format(run_id=quote(run_id, safe="")) if run_id is not None else template
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(base + path, data=payload, method=method)  # noqa: S310
    request.add_header("Accept", "application/json")
    request.add_header("Authorization", f"Bearer {_token()}")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")
    except urllib.error.URLError as error:
        fail(EXIT_PREREQUISITE, f"cannot reach the auth service: {error.reason}")
    raise AssertionError("unreachable")


def _report(status: int, body: str) -> int:
    """Print the answer, and exit 5 when the service refused.

    The service's own error WORD is printed and its status is not relayed as
    this command's exit code (D433): a caller reads `no_such_workflow` or
    `scope_not_held`, which are the two words the surface publishes.
    """
    try:
        document = json.loads(body)
    except ValueError:
        document = None
    if status >= 400:
        word = document.get("error") if isinstance(document, dict) else None
        fail(EXIT_REFUSED, f"the service refused: {word or body.strip()[:200]}")
    print(json.dumps(document if document is not None else body, indent=2, sort_keys=True))
    return EXIT_OK


def command_http(arguments: argparse.Namespace) -> int:
    if arguments.project_outputs is None:
        fail(EXIT_INPUT, f"{arguments.command} requires --project-outputs FILE")
    base = _app_base(Path(arguments.project_outputs))

    if arguments.command in ("run", "dry-run"):
        if arguments.definition is None:
            fail(EXIT_INPUT, f"{arguments.command} requires --definition NAME@VERSION")
        matched = DEFINITION_REFERENCE.match(arguments.definition)
        if matched is None:
            fail(
                EXIT_INPUT,
                f"{arguments.definition!r} is not a definition reference; a run names "
                "one as name@version, the way a step names a capability",
            )
        try:
            document = json.loads(arguments.input_document or "{}")
        except ValueError as error:
            fail(EXIT_INPUT, f"--input is not JSON: {error}")
        if not isinstance(document, dict):
            fail(
                EXIT_INPUT,
                "--input is a JSON object, and every key is a name a "
                "definition's {{input.<key>}} reference can read",
            )
        status, body = _call(
            base,
            "run",
            body={
                "name": matched.group(1),
                "version": int(matched.group(2)),
                "input": document,
                # **`dry-run` is `run` with a flag, not a fourth route.** One
                # address, one handler, one audit shape -- a separate endpoint
                # would be a second path to the same authority.
                "dry_run": arguments.command == "dry-run",
            },
        )
        return _report(status, body)

    if arguments.run is None:
        fail(EXIT_INPUT, f"{arguments.command} requires --run RUN_ID")
    status, body = _call(base, arguments.command, run_id=arguments.run)
    return _report(status, body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bin/workflow.sh", add_help=False)
    parser.add_argument("command", choices=("init", "validate", *HTTP_VERBS))
    parser.add_argument("--project", default=None)
    parser.add_argument("--project-outputs", dest="project_outputs", default=None)
    parser.add_argument("--capabilities", type=Path, default=None)
    parser.add_argument("--file", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--input", dest="input_document", default=None)
    parser.add_argument("--definition", default=None)
    parser.add_argument("--run", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.command in HTTP_VERBS:
        return command_http(arguments)

    if arguments.project is None:
        fail(EXIT_INPUT, f"{arguments.command} requires --project FILE")
    if not Path(arguments.project).is_file():
        fail(EXIT_INPUT, f"--project names no file: {arguments.project}")

    if arguments.command == "init":
        return command_init(arguments)
    return command_validate(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
