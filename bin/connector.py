#!/usr/bin/env python3
"""The work behind `bin/connector.sh` (ADR 0236, ADR 0237).

Two verbs are pure reads of a project manifest, its lock and its own files:
`init` and `validate` reach no host, no root and no render.

Three call the auth service's three admin connector routes as a HUMAN: they
hold no SQL, no route that `ROUTES` does not enumerate, and **no token** --
the credential comes from `APG_API_TOKEN` in this process's environment and is
never an argument, because an argument is a value `ps` can read (D105, D1160).
`enable` and `disable` refuse before any request unless `--confirm` repeats
`--name`: binding an agent starts runs as it, and disabling holds deliveries.

**One is root's**: `key` derives ONE connector's key from the master in the
project's ACTIVE secret generation and writes it to a new file, mode 0600,
never to standard output (D1804). A sender outside the deployment has to hold
that key; a transcript is where a secret printed to a terminal ends up.

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
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import (
    REPO_ROOT,
    config,
    connector_definition,
    connector_keys,
    naming,
    secrets_contract,
    workflow_definition,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_STATE = 4
EXIT_REFUSED = 5

#: The verbs that reach the deployment.
HTTP_VERBS = ("status", "enable", "disable")

#: **The closed table** (`bin/workflow.py`'s `ADMIN_ROUTES` shape). Three verbs,
#: three admin routes; a path this table does not name is a path this command
#: cannot reach. The inbound route `/connectors/{name}` is a SENDER's and is
#: deliberately absent: an administrator does not impersonate one.
ROUTES: dict[str, tuple[str, str]] = {
    "status": ("GET", "/admin/connectors"),
    "enable": ("POST", "/admin/connectors/{name}/enable"),
    "disable": ("POST", "/admin/connectors/{name}/disable"),
}

#: A human administrator's access token, `bin/api.py`'s variable. (S105
#: matches on the NAME; this is the name of an environment variable.)
TOKEN_VARIABLE = "APG_API_TOKEN"  # noqa: S105

REQUEST_TIMEOUT_SECONDS = 30

#: `app_private.connector.name`'s own constraint.
CONNECTOR_NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")

#: Where `key` reads generations from. A module attribute so a proof can root
#: it in a temporary directory; nothing on the command line can move it.
SECRET_ROOT = connector_keys.SECRET_ROOT

SECRET_CONTRACT = REPO_ROOT / "secrets.required.yaml"


def fail(code: int, message: str) -> None:
    print(f"connector: {message}", file=sys.stderr)
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
    """`projects/<slug>`, from `migrations.set`: connectors live beside workflows."""
    named = config.project_migration_set(document)
    return None if named is None else REPO_ROOT / named


def _definitions(root: Path | None, lock: workflow_definition.LockView) -> dict:
    if root is None:
        return {}
    try:
        return connector_definition.definitions_for(root, lock)
    except workflow_definition.DefinitionError as error:
        fail(EXIT_REFUSED, f"a definition of this set does not compile: {error.reason}")
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

HEADER = """\
# {article} {kind} connector for {key}, scaffolded from its own set.
#
# Read it before it is reviewed: it compiles as it stands, and every TODO is a
# decision a scaffold cannot make. Install it by putting it in
#   {directory}/
# and deploying -- step 6e installs it DISABLED, and an administrator enables
# it with `bin/connector.sh enable`.
"""

OUTBOUND = """\
#
# `event` must name an event this set's own migrations emit with
# app.emit_event(name, version, payload); the placeholder below compiles and
# names nothing that is emitted. The endpoint is NOT here: it is the
# deployment's, in the project manifest (D1786):
#   connectors.endpoints.{name}
---
schema_version: 1
name: {name}
version: 1
description: >-
  TODO: what the receiver does with this event.
kind: outbound
event: example.changed@1
retry:
  max: 3
  backoff_seconds: 30
"""

INBOUND = """\
#
# A signed request to POST /connectors/{name} starts a run of
#   {workflow}
# as the agent an administrator binds. The body IS the run's input: exactly the
# members the definition reads, each required. Every member is scaffolded as a
# string -- TODO: give each its real type and bound.
---
schema_version: 1
name: {name}
version: 1
description: >-
  TODO: which system sends this, and what the run it starts is for.
kind: inbound
workflow: {workflow}
body:
  members:
{members}"""

SCHEDULED = """\
#
# Starts a run of
#   {workflow}
# every `every_seconds` once enabled, as the agent an administrator binds. The
# input is literal -- a schedule has no request -- and gives exactly the keys
# the definition reads. TODO: each value below.
---
schema_version: 1
name: {name}
version: 1
description: >-
  TODO: what the scheduled run is for.
kind: scheduled
workflow: {workflow}
schedule:
  every_seconds: 3600
input:
{inputs}"""

MEMBER = """\
    {member}:
      type: string
      required: true
      max_length: 256
"""


def _first_definition(definitions: dict, *, with_input: bool) -> Any:
    """The first definition by (name, version) -- with an input, for an inbound
    one, because a body nothing reads is refused."""
    for key in sorted(definitions):
        compiled = definitions[key]
        if not with_input or workflow_definition.input_references(compiled):
            return compiled
    return None


def command_init(arguments: argparse.Namespace) -> int:
    kind = arguments.kind
    if kind not in connector_definition.KINDS:
        fail(EXIT_INPUT, f"init requires --kind {' | '.join(connector_definition.KINDS)}")
    name = arguments.name or f"example-{kind}"
    if not CONNECTOR_NAME.fullmatch(name):
        fail(
            EXIT_INPUT,
            f"{name!r} is not a connector name; the column's own constraint is "
            "^[a-z][a-z0-9-]{0,62}$",
        )
    document = _manifest(Path(arguments.project))
    root = _project_set_root(document)
    directory = (
        f"{root.relative_to(REPO_ROOT)}/{connector_definition.CONNECTORS_SUBDIR}"
        if root is not None
        else f"projects/<slug>/{connector_definition.CONNECTORS_SUBDIR}"
    )
    header = HEADER.format(
        article="An" if kind[0] in "aeiou" else "A",
        kind=kind,
        key=document["project"]["slug"] + "-" + document["project"]["environment"],
        directory=directory,
    )

    if kind == connector_definition.OUTBOUND:
        print(header + OUTBOUND.format(name=name), end="")
        return EXIT_OK

    definitions = _definitions(root, _lock(arguments))
    compiled = _first_definition(definitions, with_input=kind == connector_definition.INBOUND)
    if compiled is None:
        fail(
            EXIT_REFUSED,
            f"this project's set has no definition {_a(kind)} connector could start"
            + (" with an input to read" if kind == connector_definition.INBOUND else "")
            + ". A connector starts a definition its own set installs.",
        )
    workflow = f"{compiled.name}@{compiled.version}"
    references = sorted(workflow_definition.input_references(compiled))
    if kind == connector_definition.INBOUND:
        members = "".join(MEMBER.format(member=member) for member in references)
        print(header + INBOUND.format(name=name, workflow=workflow, members=members), end="")
        return EXIT_OK
    # A definition that reads no input gets `{}`, which is YAML for an empty
    # mapping -- exactly the keys it reads.
    inputs = "".join(f"  {member}: TODO\n" for member in references) or "  {}\n"
    print(header + SCHEDULED.format(name=name, workflow=workflow, inputs=inputs), end="")
    return EXIT_OK


def _a(kind: str) -> str:
    return f"an {kind}" if kind[0] in "aeiou" else f"a {kind}"


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def _describe(compiled: connector_definition.CompiledConnector) -> str:
    if compiled.kind == connector_definition.OUTBOUND:
        return f"event {compiled.event}"
    what = f"workflow {compiled.definition_name}@{compiled.definition_version}"
    if compiled.kind == connector_definition.SCHEDULED:
        what += f" every {compiled.every_seconds}s"
    return f"{what}  scopes: {', '.join(compiled.required_scopes) or 'none'}"


def command_validate(arguments: argparse.Namespace) -> int:
    document = _manifest(Path(arguments.project))
    root = _project_set_root(document)

    if arguments.file is not None:
        paths = [Path(arguments.file)]
    else:
        if root is None:
            print(
                "connector: this project declares no migrations.set, so it has no "
                "connectors/ directory of its own and there is nothing to validate."
            )
            return EXIT_OK
        paths = connector_definition.connectors_of(root)
        if not paths:
            print(
                f"connector: {root.relative_to(REPO_ROOT)}/"
                f"{connector_definition.CONNECTORS_SUBDIR}/ holds no connectors; this "
                "project declares none."
            )
            return EXIT_OK

    lock = _lock(arguments)
    definitions = _definitions(root, lock)

    # **Held until every file has compiled** (D1403): a success line printed as
    # it went would put "compile" on the terminal above a refusal.
    report: list[str] = []
    for path in paths:
        try:
            compiled = connector_definition.compile_file(path, lock, definitions)
        except connector_definition.ConnectorError as error:
            fail(EXIT_REFUSED, f"{path}: {error}")
        report.append(
            f"  {path.name:<24} {compiled.name} v{compiled.version}  {compiled.kind:<9} "
            f"{_describe(compiled)}"
        )

    print(
        f"connector: {len(paths)} connector(s) compile against this project's lock and definitions"
    )
    print("\n".join(report))
    print(f"  lock tools_sha256  {lock.tools_sha256}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# key (root)
# ---------------------------------------------------------------------------


def command_key(arguments: argparse.Namespace) -> int:
    """Derive ONE connector's key into a new 0600 file; never stdout (D1804).

    Every refusal of input comes before root is asked for, so a mistyped name
    costs nothing and reads nothing.
    """
    if arguments.project is None or arguments.name is None or arguments.output is None:
        fail(EXIT_INPUT, "key requires --project FILE --name NAME --output FILE")
    name = arguments.name
    if not CONNECTOR_NAME.fullmatch(name):
        fail(EXIT_INPUT, f"{name!r} is not a connector name")
    output = Path(arguments.output)
    if os.path.lexists(output):
        fail(
            EXIT_INPUT,
            f"{output} already exists. key writes a NEW file and never replaces one: a "
            "key over a file somebody else reads is a key handed to them.",
        )
    if not output.parent.is_dir():
        fail(EXIT_INPUT, f"{output.parent} is not a directory")

    document = _manifest(Path(arguments.project))
    if not config.connectors_enabled(document):
        fail(
            EXIT_REFUSED,
            "this project does not enable the connectors facility (connectors.enabled in "
            "the manifest), so it has no connector master and no key to derive.",
        )
    root = _project_set_root(document)
    declared = set()
    for path in connector_definition.connectors_of(root) if root is not None else []:
        try:
            declared.add(str(connector_definition.load(path)["name"]))
        except connector_definition.ConnectorError as error:
            fail(EXIT_REFUSED, f"{path}: {error}")
    if name not in declared:
        fail(
            EXIT_REFUSED,
            f"{name} is not a connector of this project's set "
            f"({', '.join(sorted(declared)) or 'it declares none'}); a key for it would "
            "sign for nothing.",
        )

    if os.geteuid() != 0:
        fail(
            EXIT_STATE,
            "key reads the project's root-owned secret generation and must run as root: "
            "sudo bin/connector.sh key ...",
        )
    project_key = naming.project_key(
        document["project"]["slug"], document["project"]["environment"]
    )
    try:
        contract = secrets_contract.load_secret_contract(SECRET_CONTRACT)
        path = connector_keys.master_path(project_key, contract, secret_root=SECRET_ROOT)
        key = connector_keys.derive(connector_keys.read_master(path), name)
    except connector_keys.KeyRefused as error:
        fail(error.code, str(error))
    except config.ManifestError as error:
        fail(EXIT_REFUSED, f"the secret contract does not load: {error}")

    # O_EXCL and O_NOFOLLOW: a path that appeared since the check above, or a
    # symlink planted there, is refused by the kernel rather than written through.
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        fail(EXIT_INPUT, f"{output} already exists")
    except OSError as error:
        fail(EXIT_PREREQUISITE, f"{output} cannot be created: {error.strerror}")
    try:
        os.fchmod(descriptor, 0o600)
        os.write(descriptor, (key + "\n").encode("ascii"))
    finally:
        os.close(descriptor)
    print(
        f"connector: wrote {name}'s key to {output} (mode 0600, owner {os.geteuid()}). "
        "Hand it to the sender out of band; it is printed nowhere. It changes when "
        "APG_CONNECTOR_SIGNING_KEY is replaced and the project redeployed -- every "
        "connector's key at once."
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# the three that reach a deployment
# ---------------------------------------------------------------------------


def _app_base(path: Path) -> str:
    """The deployment's app route, READ from a rendered outputs document (ADR 0002)."""
    if not path.is_file():
        fail(EXIT_INPUT, f"outputs document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(EXIT_INPUT, f"cannot read {path}: {error}")
    route = (document.get("routes") or {}).get("app")
    url = route.get("url") if isinstance(route, dict) else route
    if not isinstance(url, str) or not url:
        fail(EXIT_REFUSED, "this document publishes no app route.")
    if urlsplit(url).scheme not in ("https", "http"):
        fail(EXIT_REFUSED, f"routes.app is not a URL: {url!r}")
    return url.rstrip("/")


def _token() -> str:
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token:
        fail(
            EXIT_PREREQUISITE,
            f"{TOKEN_VARIABLE} is empty. Reading, enabling or disabling a connector is a "
            "HUMAN administrator's act, so this command needs an access token in its "
            "environment -- `bin/api.sh`'s variable, and never an argument. Log in as an "
            "administrator holding admin_connectors:read (status) or admin_connectors:write.",
        )
    return token


def _call(
    base: str,
    verb: str,
    *,
    name: str | None = None,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> tuple[int, str]:
    """One request against ONE route of `ROUTES`."""
    method, template = ROUTES[verb]
    path = template.format(name=quote(name, safe="")) if name is not None else template
    if query:
        path = f"{path}?{urlencode(query)}"
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
    """Print the document whole, or exit 5 with the service's own error WORD.

    No summary (ADR 0195): a status document read by this command and restated
    in fewer words would be a second, weaker reader of the same answer.
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
    """Every refusal of input comes BEFORE the outputs document is read and
    before the token is looked for."""
    verb = arguments.command
    if verb == "status":
        query = None
        if arguments.dead_limit is not None:
            if not arguments.dead_limit.isdigit() or not 1 <= int(arguments.dead_limit) <= 20:
                fail(EXIT_INPUT, "--dead-limit is an integer from 1 to 20")
            query = {"dead_limit": str(int(arguments.dead_limit))}
        if arguments.project_outputs is None:
            fail(EXIT_INPUT, "status requires --project-outputs FILE")
        return _report(*_call(_app_base(Path(arguments.project_outputs)), "status", query=query))

    if arguments.name is None:
        fail(EXIT_INPUT, f"{verb} requires --name NAME")
    if not CONNECTOR_NAME.fullmatch(arguments.name):
        fail(EXIT_INPUT, f"{arguments.name!r} is not a connector name")
    if arguments.confirm != arguments.name:
        fail(EXIT_INPUT, "--confirm must repeat the connector's name")
    body: dict[str, Any] | None = None
    if verb == "enable":
        agent = arguments.agent
        if agent is not None:
            try:
                agent = str(UUID(agent))
            except ValueError:
                fail(EXIT_INPUT, f"--agent {agent!r} is not an agent id")
        body = {"agent_id": agent}
    elif arguments.agent is not None:
        fail(EXIT_INPUT, "disable takes no --agent; it unbinds whichever agent is bound")
    if arguments.project_outputs is None:
        fail(EXIT_INPUT, f"{verb} requires --project-outputs FILE")
    base = _app_base(Path(arguments.project_outputs))
    return _report(*_call(base, verb, name=arguments.name, body=body))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bin/connector.sh", add_help=False)
    parser.add_argument("command", choices=("init", "validate", "key", *HTTP_VERBS))
    parser.add_argument("--project", default=None)
    parser.add_argument("--project-outputs", dest="project_outputs", default=None)
    parser.add_argument("--capabilities", type=Path, default=None)
    parser.add_argument("--file", default=None)
    parser.add_argument("--kind", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--confirm", default=None)
    parser.add_argument("--agent", default=None)
    parser.add_argument("--dead-limit", dest="dead_limit", default=None)
    parser.add_argument("--output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    if arguments.command in HTTP_VERBS:
        return command_http(arguments)
    if arguments.command == "key":
        return command_key(arguments)

    if arguments.project is None:
        fail(EXIT_INPUT, f"{arguments.command} requires --project FILE")
    if not Path(arguments.project).is_file():
        fail(EXIT_INPUT, f"--project names no file: {arguments.project}")

    if arguments.command == "init":
        return command_init(arguments)
    return command_validate(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
