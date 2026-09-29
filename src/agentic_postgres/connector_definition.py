"""A project's connectors: loaded, compiled against its lock and its definitions (ADR 0236).

A connector is a project artefact the way a workflow definition is: reviewed in
the checkout, installed by the deploy (step 6e), immutable per (name, version).
Three kinds. An **outbound** connector names an event and a retry, and the
worker delivers each such event to this deployment's endpoint (ADR 0238). An
**inbound** connector names a definition and a closed body, and a signed
request starts a run of that definition with the body as its input (ADR 0237).
A **scheduled** connector names a definition, an interval and a literal input
(ADR 0236).

**The file says WHAT; the manifest says WHERE** (D1786). A committed file is
shared by every deployment of its set -- `projects/example` is rendered by
beta and by both fixtures -- so an endpoint in it would send one deployment's
events to another's receiver. Nothing here reads, returns or records an
endpoint; `connector_install.statements` takes it as a separate argument.

**Scopes are never re-derived here.** An inbound or scheduled connector starts
a run of a definition, and the run needs what that definition needs. So the
definition is compiled with the workflow compiler against the same lock, and
its `required_scopes` are copied onto the connector: an administrator binds an
agent whose stored scopes EQUAL them (ADR 0236), and a second derivation would
be a second answer to that question.

**The body is the run's input** (D1787). An inbound body declares its members
in a closed subset, and both directions are refusals: a member the definition
never reads is a value accepted for nothing, and a reference to an input the
body does not declare is a run that fails `input_unresolved` on its first
step (the worker's `resolve`). For the same reason a member the definition
reads may not be optional (D1831): the worker has no default to resolve an
absent key to.

`check_body` is the host's reference validator for that subset. The service
has its own, `services/auth-api/app/connector_body.py`, because the image may
not import this package; a proof feeds both the same cases (D1682's pattern).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentic_postgres import config
from agentic_postgres import workflow_definition as wd

#: The schema a connector file is validated against before it is compiled.
SCHEMA_NAME = "connector.schema.json"

#: `projects/<slug>/connectors/*.yaml`. Optional, like `workflows/`: a project
#: that declares no connectors is not one with an empty directory, and step 6e
#: says which.
CONNECTORS_SUBDIR = "connectors"

OUTBOUND = "outbound"
INBOUND = "inbound"
SCHEDULED = "scheduled"
KINDS = (OUTBOUND, INBOUND, SCHEDULED)

#: The members each kind carries, and so the members every OTHER kind may not.
#: A member of another kind is refused by name rather than ignored: an inbound
#: file that carried `event` was written by someone who believed it would be
#: delivered, and installing it silently would keep that belief.
KIND_MEMBERS: dict[str, tuple[str, ...]] = {
    OUTBOUND: ("event", "retry"),
    INBOUND: ("workflow", "body"),
    SCHEDULED: ("workflow", "schedule", "input"),
}

#: `workflow: name@version`.
WORKFLOW_REFERENCE = re.compile(r"^([a-z][a-z0-9-]{0,62})@([1-9][0-9]{0,3})$")

MAX_BODY_MEMBERS = 16
MAX_STRING_LENGTH = 8192
MIN_EVERY_SECONDS = 60
MAX_EVERY_SECONDS = 86400
MAX_DELIVERY_RETRIES = 10
MAX_DELIVERY_BACKOFF_SECONDS = 3600

#: A body member's type, and the bounds each type declares.
BOUND_OF = {"string": ("max_length",), "integer": ("minimum", "maximum"), "boolean": ()}


class ConnectorError(Exception):
    """One refusal, and the member it is about (`None` for the file itself)."""

    def __init__(self, member: str | None, reason: str) -> None:
        self.member = member
        self.reason = reason
        super().__init__(reason if member is None else f"{member}: {reason}")


@dataclass(frozen=True, slots=True)
class CompiledConnector:
    """A connector ready to install: the row's values, and the body it stores.

    `body` is what `app_private.connector.body` holds: the file's own members,
    compiled -- an inbound connector's declaration under `body` (the route
    reads `body -> 'body'`), a scheduled connector's input under `input`
    (`connector_fire_due` reads `body -> 'input'`). Never an endpoint.
    """

    name: str
    version: int
    kind: str
    description: str
    source_sha256: str
    event: str | None
    definition_name: str | None
    definition_version: int | None
    required_scopes: tuple[str, ...]
    every_seconds: int | None
    retry_max: int | None
    backoff_seconds: int | None
    declaration: dict[str, Any] | None
    input: dict[str, Any] | None

    def body(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "kind": self.kind,
            "required_scopes": list(self.required_scopes),
        }
        if self.kind == OUTBOUND:
            document["event"] = self.event
            document["retry"] = {"max": self.retry_max, "backoff_seconds": self.backoff_seconds}
        else:
            document["workflow"] = f"{self.definition_name}@{self.definition_version}"
        if self.kind == INBOUND:
            document["body"] = self.declaration
        if self.kind == SCHEDULED:
            document["schedule"] = {"every_seconds": self.every_seconds}
            document["input"] = self.input
        return document

    def as_install(self) -> dict[str, Any]:
        """`app_private.connector_install`'s arguments but the endpoint, by name.

        The endpoint is the deployment's and is passed beside this, never
        inside it: a compiled connector is the same object on every deployment.
        """
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "body": self.body(),
            "source_sha256": self.source_sha256,
            "event": self.event,
            "definition_name": self.definition_name,
            "definition_version": self.definition_version,
            "required_scopes": self.required_scopes,
            "every_seconds": self.every_seconds,
            "retry_max": self.retry_max,
            "backoff_seconds": self.backoff_seconds,
        }


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def connectors_of(project_set_root: Path) -> list[Path]:
    """`<root>/connectors/*.yaml`, sorted; an empty list when there is no directory."""
    directory = Path(project_set_root) / CONNECTORS_SUBDIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.yaml"))


def load(path: Path) -> dict[str, Any]:
    """Read one connector file and validate its SHAPE. Nothing about the lock."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ConnectorError(None, f"cannot be read: {error}") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConnectorError(None, f"is not YAML: {error}") from error
    if not isinstance(document, dict):
        raise ConnectorError(None, "is not a mapping")
    try:
        config.validate_against_schema(document, SCHEMA_NAME)
    except config.ManifestError as error:
        raise ConnectorError(None, str(error)) from error
    return document


def definitions_for(
    project_set_root: Path, lock: wd.LockView
) -> dict[tuple[str, int], wd.Compiled]:
    """Every definition of the set, compiled against `lock`, by (name, version).

    A definition that does not compile raises the workflow compiler's own
    refusal: step 6d compiled the same files against the same lock a moment
    earlier and would already have refused the deploy.
    """
    compiled: dict[tuple[str, int], wd.Compiled] = {}
    for path in wd.definitions_of(project_set_root):
        definition = wd.compile_file(path, lock)
        compiled[(definition.name, definition.version)] = definition
    return compiled


# ---------------------------------------------------------------------------
# Compiling
# ---------------------------------------------------------------------------


def _a(kind: str) -> str:
    return f"an {kind}" if kind[0] in "aeiou" else f"a {kind}"


def _members_of_kind(document: dict[str, Any], kind: str) -> None:
    for other, members in KIND_MEMBERS.items():
        if other == kind:
            continue
        for member in members:
            if member in document and member not in KIND_MEMBERS[kind]:
                raise ConnectorError(
                    member, f"is {_a(other)} connector's member and this connector is {kind}"
                )
    for member in KIND_MEMBERS[kind]:
        if member not in document:
            raise ConnectorError(member, f"is required on {_a(kind)} connector")


def _definition(
    document: dict[str, Any], definitions: Mapping[tuple[str, int], wd.Compiled]
) -> wd.Compiled:
    reference = str(document["workflow"])
    match = WORKFLOW_REFERENCE.fullmatch(reference)
    if match is None:
        raise ConnectorError(
            "workflow", f"{reference!r} is not a definition reference; one is name@version"
        )
    key = (match.group(1), int(match.group(2)))
    if key not in definitions:
        carried = ", ".join(f"{name}@{version}" for name, version in sorted(definitions)) or "none"
        raise ConnectorError(
            "workflow",
            f"names {reference}, which is not a definition of this set's workflows/ "
            f"(it has: {carried}). A connector starts a definition its own set installs.",
        )
    return definitions[key]


def _declaration(document: dict[str, Any], definition: wd.Compiled) -> dict[str, Any]:
    """The inbound body, checked against the definition in both directions."""
    members = (document.get("body") or {}).get("members") or {}
    if not members:
        raise ConnectorError("body", "declares no members")
    if len(members) > MAX_BODY_MEMBERS:
        raise ConnectorError("body", f"declares {len(members)} members; at most {MAX_BODY_MEMBERS}")
    for name, member in members.items():
        kind = member["type"]
        allowed = set(BOUND_OF[kind])
        carried = {key for key in ("max_length", "minimum", "maximum") if key in member}
        if carried - allowed:
            raise ConnectorError(
                f"body.members.{name}",
                f"is a {kind} and carries {', '.join(sorted(carried - allowed))}",
            )
        if kind == "string" and "max_length" not in member:
            raise ConnectorError(f"body.members.{name}", "is a string and declares no max_length")
        if kind == "integer":
            if "minimum" not in member or "maximum" not in member:
                raise ConnectorError(
                    f"body.members.{name}", "is an integer and declares no minimum and maximum"
                )
            if member["minimum"] > member["maximum"]:
                raise ConnectorError(f"body.members.{name}", "declares minimum above maximum")

    referenced = wd.input_references(definition)
    workflow = document["workflow"]
    unread = sorted(set(members) - referenced)
    if unread:
        raise ConnectorError(
            "body",
            f"declares {', '.join(unread)}, which {workflow} never reads as {{{{input.<m>}}}}. "
            "The body is the run's input; a member nothing reads is accepted for nothing",
        )
    undeclared = sorted(referenced - set(members))
    if undeclared:
        raise ConnectorError(
            "body",
            f"does not declare {', '.join(undeclared)}, which {workflow} reads as "
            "{{input.<key>}}; every run it started would fail input_unresolved",
        )
    optional = sorted(name for name, member in members.items() if not member["required"])
    if optional:
        raise ConnectorError(
            "body",
            f"declares {', '.join(optional)} not required, and {workflow} reads every member: "
            "a request without one would start a run that fails input_unresolved, because the "
            "worker has no default to resolve an absent key to (D1831)",
        )
    return {"members": {name: dict(members[name]) for name in sorted(members)}}


def _input(document: dict[str, Any], definition: wd.Compiled) -> dict[str, Any]:
    """A scheduled connector's input: literals, exactly the keys the definition reads."""
    supplied = document.get("input") or {}
    for key, value in supplied.items():
        if isinstance(value, bool | int):
            continue
        if not isinstance(value, str) or wd.BRACES.search(value):
            raise ConnectorError(
                f"input.{key}",
                "is not a literal; a schedule has no request and no prior step, so there is "
                "nothing for a reference to resolve against",
            )
    referenced = wd.input_references(definition)
    workflow = document["workflow"]
    missing = sorted(referenced - set(supplied))
    if missing:
        raise ConnectorError(
            "input",
            f"does not give {', '.join(missing)}, which {workflow} reads; every scheduled run "
            "would fail input_unresolved",
        )
    unread = sorted(set(supplied) - referenced)
    if unread:
        raise ConnectorError("input", f"gives {', '.join(unread)}, which {workflow} never reads")
    return {key: supplied[key] for key in sorted(supplied)}


def compile(
    document: dict[str, Any],
    lock: wd.LockView,
    definitions: Mapping[tuple[str, int], wd.Compiled],
    *,
    source_sha256: str,
) -> CompiledConnector:
    """Resolve one connector against the set's definitions, or refuse naming the member.

    `lock` is the one the definitions were compiled against; it is taken so
    that a caller cannot pair a connector with definitions compiled against
    some other lock without saying so, and its digest is checked against
    theirs.
    """
    for key, definition in definitions.items():
        if definition.lock_tools_sha256 != lock.tools_sha256:
            raise ConnectorError(
                None,
                f"definition {key[0]}@{key[1]} was compiled against another lock",
            )
    kind = document["kind"]
    if kind not in KINDS:
        raise ConnectorError("kind", f"{kind!r} is not one of {', '.join(KINDS)}")
    _members_of_kind(document, kind)

    event = definition_name = None
    definition_version = every_seconds = retry_max = backoff_seconds = None
    declaration = supplied = None
    scopes: tuple[str, ...] = ()

    if kind == OUTBOUND:
        event = str(document["event"])
        if wd.EVENT_REFERENCE.fullmatch(event) is None:
            raise ConnectorError(
                "event",
                f"{event!r} is not an event reference; an outbound connector names one as "
                "name@version, because an event whose shape changed is a new version",
            )
        retry = document["retry"]
        retry_max, backoff_seconds = int(retry["max"]), int(retry["backoff_seconds"])
        if not 0 <= retry_max <= MAX_DELIVERY_RETRIES:
            raise ConnectorError("retry", f"max {retry_max} is outside 0..{MAX_DELIVERY_RETRIES}")
        if not 1 <= backoff_seconds <= MAX_DELIVERY_BACKOFF_SECONDS:
            raise ConnectorError(
                "retry",
                f"backoff_seconds {backoff_seconds} is outside 1..{MAX_DELIVERY_BACKOFF_SECONDS}",
            )
    else:
        definition = _definition(document, definitions)
        definition_name, definition_version = definition.name, definition.version
        scopes = definition.required_scopes
        if kind == INBOUND:
            declaration = _declaration(document, definition)
        else:
            every_seconds = int(document["schedule"]["every_seconds"])
            if not MIN_EVERY_SECONDS <= every_seconds <= MAX_EVERY_SECONDS:
                raise ConnectorError(
                    "schedule",
                    f"every_seconds {every_seconds} is outside "
                    f"{MIN_EVERY_SECONDS}..{MAX_EVERY_SECONDS}",
                )
            supplied = _input(document, definition)

    return CompiledConnector(
        name=document["name"],
        version=int(document["version"]),
        kind=kind,
        description=document["description"],
        source_sha256=source_sha256,
        event=event,
        definition_name=definition_name,
        definition_version=definition_version,
        required_scopes=tuple(scopes),
        every_seconds=every_seconds,
        retry_max=retry_max,
        backoff_seconds=backoff_seconds,
        declaration=declaration,
        input=supplied,
    )


def compile_file(
    path: Path, lock: wd.LockView, definitions: Mapping[tuple[str, int], wd.Compiled]
) -> CompiledConnector:
    """`load` + `compile`, with the digest taken from the bytes that were read."""
    document = load(path)
    return compile(document, lock, definitions, source_sha256=wd.source_digest(path))


# ---------------------------------------------------------------------------
# The body subset, the host's reference validator (D1787)
# ---------------------------------------------------------------------------


def check_body(declaration: dict[str, Any], body: Any) -> str | None:
    """`None` when `body` is inside `declaration`, else the first refusal.

    The refusal is a token and, for a declared member, its NAME -- never a
    value, and never an undeclared member's name, which is caller text. The
    order is fixed so that the service's validator can be held to the same
    verdict case by case: declared members in name order, then anything else.
    """
    if not isinstance(body, dict):
        return "not_an_object"
    members = declaration.get("members") or {}
    for name in sorted(members):
        member = members[name]
        if name not in body:
            if member.get("required") is True:
                return f"missing:{name}"
            continue
        value = body[name]
        kind = member.get("type")
        if kind == "string":
            if not isinstance(value, str):
                return f"type:{name}"
            if len(value) > int(member.get("max_length", MAX_STRING_LENGTH)):
                return f"too_long:{name}"
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"type:{name}"
            if not int(member["minimum"]) <= value <= int(member["maximum"]):
                return f"out_of_range:{name}"
        elif kind == "boolean":
            if not isinstance(value, bool):
                return f"type:{name}"
        else:
            return f"type:{name}"
    if set(body) - set(members):
        return "unexpected_member"
    return None


__all__ = [
    "CONNECTORS_SUBDIR",
    "INBOUND",
    "KINDS",
    "KIND_MEMBERS",
    "MAX_BODY_MEMBERS",
    "OUTBOUND",
    "SCHEDULED",
    "SCHEMA_NAME",
    "WORKFLOW_REFERENCE",
    "CompiledConnector",
    "ConnectorError",
    "check_body",
    "compile",
    "compile_file",
    "connectors_of",
    "definitions_for",
    "load",
]
