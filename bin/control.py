#!/usr/bin/env python
"""The control plane's operator verbs: adopt, registry, totp-reset (ADR 0251, D2068).

Invoked by ``bin/control.sh``, which is the documented entry point.

**The registry is the control plane's own record, written by the person who
holds root.** ``adopt`` copies five pointers out of a project's DEPLOYED
document into ``app.control_projects``; ``registry`` compares every row with
every deployed document; ``totp-reset`` removes one person's second factor.
Each calls a function the control set grants to nobody (D2093) -- as the
cluster's superuser, through the control project's database container, with
the container and database read from the control project's deployed document
(D1184) and every value passed as a ``psql`` variable, never interpolated.

**The control project is found, never named**: the one deployed document under
the state root whose ``control.enabled`` is true (outputs 20, D2068). A version
19 document predates the facility and so does not enable it. Two enabling
documents is exit 5. A document that cannot be read might be the control
project: ``adopt`` and ``totp-reset`` are decisions, and refuse (exit 6) rather
than act on a search they could not finish; ``registry`` is a report, and
reports the unreadable document as undetermined (ADR 0195: a decision may fail
closed, a report may not). ``--confirm`` must equal the control project's key,
exactly.

Exit codes: 0 adopted, reset, or all agree; 2 invalid input; 3 not root, no
deployed document, no control project, or no docker; 5 the database refused,
two control projects, or a difference; 6 something could not be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import container_exec, deployed_output  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6

#: Where the deployed documents live; a proof points it at a directory it owns.
STATE_ROOT = deployed_output.PROJECT_STATE_ROOT

#: The outputs version that first records the facility. An older document was
#: written by a release that had no control plane, so it enables none.
CONTROL_SINCE_VERSION = 20

#: What `adopt` copies and `registry` compares, in the order printed. The first
#: three are `project.*` members, the last two top-level members.
FIELDS = ("slug", "environment", "domain", "template_version", "source_commit")

#: A project key as `naming` derives one: what may be joined onto STATE_ROOT.
_KEY = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

ADOPT_SQL = (
    "SELECT app.control_adopt_project(:'key', :'organization'::uuid, :'slug', "
    ":'environment', :'domain', :'template_version', :'source_commit');"
)
REGISTRY_SQL = (
    "SELECT coalesce(json_agg(r ORDER BY r.key), '[]'::json) FROM app.control_registry_rows() r;"
)
TOTP_RESET_SQL = "SELECT app.control_totp_reset(:'username');"

#: How long one call may take; the bound exists so a hung cluster is reported.
TIMEOUT_SECONDS = 120

#: The words `registry` prints for each outcome; `--json` carries the keys.
OUTCOME_TEXT = {
    "agrees": "agrees",
    "differs": "differs",
    "not_in_registry": "not in the registry",
    "no_deployed_document": "no deployed document",
    "undetermined": "could not determine",
}


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class Reading(NamedTuple):
    """One directory under the state root: its document, or why there is none."""

    key: str
    document: dict[str, Any] | None
    reason: str | None = None
    missing: bool = False


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed documents are root-owned and the registry is "
            "reached through the control project's database container as its superuser.",
        )


def read_one(key: str) -> Reading:
    path = deployed_output.deployed_path(key, root=STATE_ROOT)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Reading(key, None, "no deployed document", missing=True)
    except OSError:
        return Reading(key, None, "the deployed document could not be read")
    except ValueError:
        return Reading(key, None, "the deployed document is not valid JSON")
    try:
        return Reading(key, deployed_output.read_deployed_document(raw))
    except ValueError as error:
        return Reading(key, None, str(error))


def read_all() -> list[Reading]:
    """Every directory under the state root, sorted -- a directory is a project the
    deploy established, and one without a document is reported, never skipped."""
    try:
        keys = sorted(path.name for path in STATE_ROOT.iterdir() if path.is_dir())
    except FileNotFoundError as error:
        raise OperatorError(
            EXIT_PREREQUISITE,
            f"no deployed project enables the control facility ({STATE_ROOT} does not exist)",
        ) from error
    except OSError as error:
        raise OperatorError(EXIT_UNKNOWN, f"{STATE_ROOT} could not be listed: {error}") from error
    return [read_one(key) for key in keys]


def enables_control(document: dict[str, Any]) -> bool | None:
    """True or false from the document; None when it says something unreadable."""
    control = document.get("control")
    if control is None and document.get("schema_version", 0) < CONTROL_SINCE_VERSION:
        return False
    if not isinstance(control, dict) or not isinstance(control.get("enabled"), bool):
        return None
    return control["enabled"]


def find_control(readings: list[Reading], *, decision: bool) -> Reading:
    """The one reading whose document enables the facility, or an OperatorError."""
    enabling = [r for r in readings if r.document is not None and enables_control(r.document)]
    unread = [f"{r.key}: {r.reason}" for r in readings if r.document is None and not r.missing] + [
        f"{r.key}: the document's control member is not readable"
        for r in readings
        if r.document is not None and enables_control(r.document) is None
    ]
    if len(enabling) > 1:
        raise OperatorError(
            EXIT_REFUSED,
            "two deployed projects enable the control facility: "
            + ", ".join(r.key for r in enabling),
        )
    if unread and (decision or not enabling):
        raise OperatorError(
            EXIT_UNKNOWN,
            "which deployed project enables the control facility could not be determined; "
            + "; ".join(unread),
        )
    if not enabling:
        raise OperatorError(EXIT_PREREQUISITE, "no deployed project enables the control facility")
    return enabling[0]


def document_fields(key: str, document: dict[str, Any]) -> tuple[dict[str, str] | None, str | None]:
    """The five pointers, or the reason they cannot be read from this document."""
    project = document.get("project")
    if not isinstance(project, dict):
        return None, "the document names no project"
    if project.get("key") != key:
        return None, f"the document under {key}/ names project {project.get('key')!r}"
    values = {
        "slug": project.get("slug"),
        "environment": project.get("environment"),
        "domain": project.get("domain"),
        "template_version": document.get("template_version"),
        "source_commit": document.get("source_commit"),
    }
    absent = [name for name in FIELDS if not isinstance(values[name], str) or not values[name]]
    if absent:
        return None, "the document carries no " + ", ".join(absent)
    return {name: str(values[name]) for name in FIELDS}, None


def target(document: dict[str, Any]) -> tuple[str, str]:
    database = document.get("database") or {}
    container, name = database.get("container"), database.get("name")
    if not container or not name:
        raise OperatorError(
            EXIT_PREREQUISITE, "the control project's deployed document names no database container"
        )
    return str(container), str(name)


def psql(container: str, database: str, sql: str, *variables: str):
    argv = ["psql", "-U", "postgres", "-d", database, "-X", "-qtA", "-v", "ON_ERROR_STOP=1"]
    for variable in variables:
        argv += ["-v", variable]
    return container_exec.run(container, *argv, "-f", "-", input=sql, timeout=TIMEOUT_SECONDS)


def require_confirmation(confirm: str, control: Reading, *, nothing: str) -> None:
    if confirm != control.key:
        raise OperatorError(
            EXIT_INPUT,
            f"--confirm must be the control project's key exactly ({control.key}); {nothing}",
        )


def refused(done: subprocess.CompletedProcess, sentence: str) -> int:
    for line in (done.stderr or "").strip().splitlines():
        print(line, file=sys.stderr)
    print(f"control: {sentence}", file=sys.stderr)
    return EXIT_REFUSED


def adopt(key: str, *, organization: str, confirm: str) -> int:
    if not _KEY.match(key):
        raise OperatorError(EXIT_INPUT, f"not a project key: {key!r}")
    try:
        organization = str(uuid.UUID(organization))
    except ValueError as error:
        raise OperatorError(
            EXIT_INPUT, f"--organization is not a uuid: {organization!r}"
        ) from error

    require_root()
    readings = read_all()
    control = find_control(readings, decision=True)
    require_confirmation(confirm, control, nothing="nothing was adopted")

    reading = next((r for r in readings if r.key == key), None)
    if reading is None or reading.missing:
        path = deployed_output.deployed_path(key, root=STATE_ROOT)
        raise OperatorError(EXIT_PREREQUISITE, f"no deployed document for {key}: {path}")
    if reading.document is None:
        raise OperatorError(EXIT_PREREQUISITE, f"cannot adopt {key}: {reading.reason}")
    fields, reason = document_fields(key, reading.document)
    if fields is None:
        raise OperatorError(EXIT_PREREQUISITE, f"cannot adopt {key}: {reason}")

    container, database = target(control.document or {})
    variables = [f"key={key}", f"organization={organization}"]
    variables += [f"{name}={fields[name]}" for name in FIELDS]
    try:
        done = psql(container, database, ADOPT_SQL, *variables)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(
            EXIT_UNKNOWN,
            f"control_adopt_project did not answer ({type(error).__name__}); whether {key} "
            "was adopted is not known -- read `control.sh registry`",
        ) from error
    if done.returncode != 0:
        return refused(done, f"the registry refused {key}; nothing was adopted")
    print(f"control {control.key} -- adopted {key} under organisation {organization}")
    for name in FIELDS:
        print(f"  {name:<16}  {fields[name]}")
    return EXIT_OK


def read_registry(control: Reading) -> list[dict[str, Any]]:
    """`control_registry_rows()`, or OperatorError(6) naming why it could not be read."""
    container, database = target(control.document or {})
    try:
        done = psql(container, database, REGISTRY_SQL)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(EXIT_UNKNOWN, f"the registry could not be read: {error}") from error
    if done.returncode != 0:
        reason = (done.stderr or "").strip().splitlines()
        raise OperatorError(
            EXIT_UNKNOWN,
            "the registry could not be read: "
            + (reason[-1] if reason else "the cluster did not answer"),
        )
    try:
        rows = json.loads(done.stdout.strip())
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and all(isinstance(row.get(n), str) for n in ("key", *FIELDS))
        for row in rows
    ):
        raise OperatorError(
            EXIT_UNKNOWN,
            "the registry could not be read: the reading did not arrive in the shape asked for",
        )
    return rows


def compare(rows: list[dict[str, Any]], readings: list[Reading]) -> list[dict[str, Any]]:
    """One outcome per key in either the registry or the state root."""
    by_row = {row["key"]: row for row in rows}
    by_key = {reading.key: reading for reading in readings}
    outcomes = []
    for key in sorted(set(by_row) | set(by_key)):
        row, reading = by_row.get(key), by_key.get(key)
        outcome: dict[str, Any] = {"project": key, "fields": [], "reason": None}
        if reading is None or reading.missing:
            outcome["outcome"] = "no_deployed_document"
        elif reading.document is None:
            outcome.update(outcome="undetermined", reason=reading.reason)
        else:
            fields, reason = document_fields(key, reading.document)
            if fields is None:
                outcome.update(outcome="undetermined", reason=reason)
            elif row is None:
                outcome["outcome"] = "not_in_registry"
            else:
                differing = [name for name in FIELDS if row[name] != fields[name]]
                outcome.update(outcome="differs" if differing else "agrees", fields=differing)
        outcomes.append(outcome)
    return outcomes


def registry(*, as_json: bool) -> int:
    require_root()
    readings = read_all()
    control = find_control(readings, decision=False)
    outcomes = compare(read_registry(control), readings)
    if as_json:
        print(json.dumps({"control_project": control.key, "projects": outcomes}, indent=2))
    else:
        print(f"registry of {control.key}")
        width = max(len(o["project"]) for o in outcomes)
        for o in outcomes:
            text = OUTCOME_TEXT[o["outcome"]]
            if o["fields"]:
                text += ": " + ", ".join(o["fields"])
            elif o["reason"]:
                text += ": " + o["reason"]
            print(f"  {o['project']:<{width}}  {text}")
    kinds = {o["outcome"] for o in outcomes}
    if "undetermined" in kinds:
        return EXIT_UNKNOWN
    return EXIT_OK if kinds == {"agrees"} else EXIT_REFUSED


def totp_reset(username: str, *, confirm: str) -> int:
    if not username or not username.isprintable() or len(username) > 128:
        raise OperatorError(EXIT_INPUT, "--username is one printable account name")

    require_root()
    control = find_control(read_all(), decision=True)
    require_confirmation(confirm, control, nothing="no factor was removed")

    container, database = target(control.document or {})
    try:
        done = psql(container, database, TOTP_RESET_SQL, f"username={username}")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(
            EXIT_UNKNOWN,
            f"control_totp_reset did not answer ({type(error).__name__}); whether a factor "
            "was removed is not known",
        ) from error
    if done.returncode != 0:
        return refused(done, "control_totp_reset did not run; no factor was removed")
    answer = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    if answer == "t":
        print(f"control {control.key} -- removed the second factor of {username}")
        return EXIT_OK
    if answer == "f":
        # The function answers false for an account with no factor and for no
        # account at all; the sentence says both rather than guess which.
        print(
            f"control {control.key} -- no second factor is enrolled for {username} "
            "(or no account has that name); nothing was removed"
        )
        return EXIT_OK
    raise OperatorError(
        EXIT_UNKNOWN,
        "control_totp_reset answered in a shape nobody asked for; whether a "
        "factor was removed is not known",
    )


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="control.sh", add_help=False)
    verbs = top.add_subparsers(dest="verb", required=True)
    adopt_verb = verbs.add_parser("adopt", add_help=False)
    adopt_verb.add_argument("--project", required=True)
    adopt_verb.add_argument("--organization", required=True)
    adopt_verb.add_argument("--confirm", required=True)
    registry_verb = verbs.add_parser("registry", add_help=False)
    registry_verb.add_argument("--json", action="store_true")
    reset_verb = verbs.add_parser("totp-reset", add_help=False)
    reset_verb.add_argument("--username", required=True)
    reset_verb.add_argument("--confirm", required=True)
    return top


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
    except SystemExit:
        return EXIT_INPUT
    try:
        if arguments.verb == "adopt":
            return adopt(
                arguments.project, organization=arguments.organization, confirm=arguments.confirm
            )
        if arguments.verb == "registry":
            return registry(as_json=arguments.json)
        return totp_reset(arguments.username, confirm=arguments.confirm)
    except OperatorError as error:
        print(f"control: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
