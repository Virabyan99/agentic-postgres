#!/usr/bin/env python
"""The control plane's operator verbs: adopt, registry, status, totp-reset (ADR 0251, D2068).

Invoked by ``bin/control.sh``, which is the documented entry point.

**The registry is the control plane's own record, written by the person who
holds root.** ``adopt`` copies five pointers out of a project's DEPLOYED
document into ``app.control_projects``; ``registry`` compares every row with
every deployed document; ``totp-reset`` removes one person's second factor.
Each of those calls a function the control set grants to nobody (D2093) -- as the
cluster's superuser, through the control project's database container, with
the container and database read from the control project's deployed document
(D1184) and every value passed as a ``psql`` variable, never interpolated.

**The control project is found, never named**: the one deployed document under
the state root whose ``control.enabled`` is true (outputs 20, D2068) --
``agentic_postgres.control_registry.find_control``, which ``bin/reconciler.sh``
uses too (D2168). A version 19 document predates the facility and so does not
enable it. Two enabling documents is exit 5. A document that cannot be read might be the control
project: ``adopt`` and ``totp-reset`` are decisions, and refuse (exit 6) rather
than act on a search they could not finish; ``registry`` is a report, and
reports the unreadable document as undetermined (ADR 0195: a decision may fail
closed, a report may not). ``--confirm`` must equal the control project's key,
exactly.

**A deleted project** (Session 38, D2167): the reconciler marks its row
``deleted_at``. ``registry`` reads such a row as ``agrees (deleted)`` when no
document is deployed under the key and the slot's tombstone is present, and as
``differs: deleted`` when a document is still deployed there.

**A prepared slot** (Session 39, D2341): a key with no row and no document
whose slot ``slot.sh prepare`` prepared -- its slot manifest written and its
bootstrap state in the state root -- reads ``prepared (slot)``, agreeing. It is
the state between a slot's bootstrap and its creation, and it commits nothing.
Any other key with no row and no document is still a difference.

**status** (Session 46, ADR 0293): who the customers are and what state each
project is in -- organisations, projects, open operations, branches, slots and
the last day's notifications, one SELECT per section and nothing written. A
project's state is ``control_states.project_state``, the service's own
function over the operation history (D704). A section that could not be read
is printed as such and the others still are; the exit is then 6.

Exit codes: 0 adopted, reset, all agree, or every status section read; 2 invalid
input; 3 not root, no deployed document, no control project, or no docker; 5 the
database refused, two control projects, or a difference; 6 something could not
be read.
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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    bootstrap_state,
    container_exec,
    control_states,
    deployed_output,
    slot,
)
from agentic_postgres.control_registry import (  # noqa: E402
    CONTROL_SINCE_VERSION,
    FIELDS,
    OperatorError,
    Reading,
    document_endpoints,
    document_fields,
    enables_control,
    find_control,
    target,
)
from agentic_postgres.control_registry import read_all as control_registry_read_all  # noqa: E402
from agentic_postgres.control_registry import read_one as control_registry_read_one  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_REFUSED = 5
EXIT_UNKNOWN = 6

#: Where the deployed documents and the slots' files live; a proof points them
#: at directories it owns.
STATE_ROOT = deployed_output.PROJECT_STATE_ROOT
SLOT_ROOT = slot.SLOT_ROOT

#: `control_registry` holds the rule and the five pointers (D2168); named here
#: so this command's readers keep finding them where they always were.
__all__ = [
    "CONTROL_SINCE_VERSION",
    "FIELDS",
    "OperatorError",
    "Reading",
    "document_fields",
    "enables_control",
    "find_control",
    "main",
    "target",
]

#: A project key as `naming` derives one: what may be joined onto STATE_ROOT.
_KEY = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

#: Session 39 (D2351): the document's `database.public` by name, NULL for a
#: document that carries none -- so an operator's re-adoption never erases
#: doors the reconciler recorded, and the other optional members stay unnamed.
ADOPT_SQL = (
    "SELECT app.control_adopt_project(:'key', :'organization'::uuid, :'slug', "
    ":'environment', :'domain', :'template_version', :'source_commit', "
    "p_endpoints => nullif(:'endpoints', '')::jsonb);"
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
    "deleted": "agrees (deleted)",
    "prepared": "prepared (slot)",
}

#: The outcomes `registry` counts as agreement (exit 0).
AGREEING = frozenset({"agrees", "deleted", "prepared"})


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed documents are root-owned and the registry is "
            "reached through the control project's database container as its superuser.",
        )


def read_one(key: str) -> Reading:
    return control_registry_read_one(key, root=STATE_ROOT)


def read_all() -> list[Reading]:
    """Every directory under the state root (``control_registry.read_all``)."""
    return control_registry_read_all(root=STATE_ROOT)


def tombstone(key: str) -> bool | None:
    """Whether the slot `key` was consumed by a deletion: True, False, or None
    when it could not be read. A key that is not a slot's has no tombstone."""
    try:
        path = slot.slot_directory(key, root=SLOT_ROOT) / slot.CONSUMED
    except ValueError:
        return False
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return True


def prepared_slot(key: str) -> bool | None:
    """Whether `key` is a slot prepared and not yet created (D2341): True,
    False, or None when it could not be read. Both halves of a preparation are
    read -- the slot manifest `slot.sh prepare` writes and the bootstrap state
    the provider half writes into the state root -- and a key that is not a
    slot's is never one."""
    try:
        directory = slot.slot_directory(key, root=SLOT_ROOT)
    except ValueError:
        return False
    try:
        os.lstat(directory / slot.MANIFEST)
        os.lstat(STATE_ROOT / key / bootstrap_state.STATE_FILENAME)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return True


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
    endpoints = document_endpoints(reading.document)
    variables.append(f"endpoints={endpoints}")
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


def cluster_said(done: subprocess.CompletedProcess) -> str:
    """The cluster's reason for a refusal: its ``ERROR:`` line, from the word on.
    psql follows that line with the statement and a caret under the fault
    (rig 46c), so the LAST line names nothing; with no ``ERROR:`` line -- a
    connection that failed -- the last line is the reason."""
    lines = (done.stderr or "").strip().splitlines()
    for line in lines:
        if "ERROR:" in line:
            return line[line.index("ERROR:") :]
    return lines[-1] if lines else "the cluster did not answer"


def read_registry(control: Reading) -> list[dict[str, Any]]:
    """`control_registry_rows()`, or OperatorError(6) naming why it could not be read."""
    container, database = target(control.document or {})
    try:
        done = psql(container, database, REGISTRY_SQL)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(EXIT_UNKNOWN, f"the registry could not be read: {error}") from error
    if done.returncode != 0:
        raise OperatorError(EXIT_UNKNOWN, "the registry could not be read: " + cluster_said(done))
    try:
        rows = json.loads(done.stdout.strip())
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(
        isinstance(row, dict)
        and all(isinstance(row.get(n), str) for n in ("key", *FIELDS))
        and isinstance(row.get("deleted_at"), (str, type(None)))
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
        if row is not None and row.get("deleted_at"):
            # D2167: the reconciler deleted it. Agreement is no document AND
            # the slot's tombstone; a document still deployed is a difference.
            consumed = tombstone(key) if reading is None or reading.missing else True
            if reading is not None and not reading.missing:
                outcome.update(outcome="differs", fields=["deleted"])
            elif consumed is None:
                outcome.update(
                    outcome="undetermined", reason="the slot's tombstone could not be read"
                )
            elif consumed:
                outcome["outcome"] = "deleted"
            else:
                outcome.update(outcome="differs", fields=["tombstone"])
        elif row is None and reading is not None and reading.missing:
            # D2341: no row and no document is a difference -- unless it is a
            # slot between its bootstrap and its creation.
            prepared = prepared_slot(key)
            if prepared is None:
                outcome.update(
                    outcome="undetermined", reason="the slot's preparation could not be read"
                )
            else:
                outcome["outcome"] = "prepared" if prepared else "no_deployed_document"
        elif reading is None or reading.missing:
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
    return EXIT_OK if kinds and kinds <= AGREEING else EXIT_REFUSED


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


# -- status (ADR 0293) ------------------------------------------------------------

#: `status`'s sections, each ONE SELECT answering one JSON array, run as the
#: cluster's superuser -- row security does not bind it (`0001:610-613`). No
#: write, no function of the control set, and no column holding a hash, a key,
#: a token, an address or a credential: each SELECT names its columns.
#: `projects` carries each project's operations OLDEST FIRST, in the order the
#: service reads them (`control_project_operations`, 0004), because the state
#: is derived from them here, by the service's own function -- never in SQL.
STATUS_SECTIONS: dict[str, str] = {
    "organizations": (
        "SELECT coalesce(json_agg(r ORDER BY r.name, r.id), '[]'::json) FROM ("
        "SELECT o.id, o.name, o.plan, "
        "array(SELECT a.username FROM app.control_memberships m "
        "JOIN app.control_accounts a ON a.user_id = m.user_id "
        "WHERE m.organization_id = o.id AND m.role = 'owner' ORDER BY a.username) AS owners, "
        "(SELECT count(*) FROM app.control_projects p "
        "WHERE p.organization_id = o.id AND p.deleted_at IS NULL) AS projects, "
        "(SELECT l.value FROM app.control_plan_limits l "
        "WHERE l.plan = o.plan AND l.entitlement = 'projects_active') AS projects_limit "
        "FROM app.control_organizations o) r;"
    ),
    "projects": (
        "SELECT coalesce(json_agg(r ORDER BY r.key), '[]'::json) FROM ("
        "SELECT p.key, o.name AS organization, p.slot, p.profile, p.deleted_at, "
        "array(SELECT json_build_object('type', op.type, 'status', op.status, "
        "'error_code', op.error_code, 'created_at', op.created_at) "
        "FROM app.control_operations op WHERE op.project_key = p.key "
        "ORDER BY op.created_at, op.id) AS history "
        "FROM app.control_projects p "
        "JOIN app.control_organizations o ON o.id = p.organization_id) r;"
    ),
    "operations": (
        "SELECT coalesce(json_agg(r ORDER BY r.created_at, r.id), '[]'::json) FROM ("
        "SELECT op.id, o.name AS organization, op.project_key, op.type, op.status, op.step, "
        "op.created_at, op.started_at FROM app.control_operations op "
        "JOIN app.control_organizations o ON o.id = op.organization_id "
        "WHERE op.status IN ('pending', 'running')) r;"
    ),
    "branches": (
        "SELECT coalesce(json_agg(r ORDER BY r.project_key, r.name), '[]'::json) FROM ("
        "SELECT b.project_key, b.name, b.state, b.expires_at FROM app.control_branches b "
        "WHERE b.state <> 'deleted') r;"
    ),
    "slots": (
        "SELECT coalesce(json_agg(r ORDER BY r.state), '[]'::json) FROM ("
        "SELECT s.state, count(*) AS slots FROM app.control_slots s GROUP BY s.state) r;"
    ),
    "notifications": (
        "SELECT coalesce(json_agg(r ORDER BY r.kind), '[]'::json) FROM ("
        "SELECT n.kind, count(*) AS notifications FROM app.control_notifications n "
        "WHERE n.created_at > now() - interval '24 hours' GROUP BY n.kind) r;"
    ),
}

_TEXT = (str,)
_TEXT_OR_NULL = (str, type(None))

#: The members each section's rows must carry, and their JSON types: a reading
#: in any other shape is a section that could not be read, never an empty one.
STATUS_SHAPES: dict[str, dict[str, tuple[type, ...]]] = {
    "organizations": {
        "id": _TEXT,
        "name": _TEXT,
        "plan": _TEXT,
        "owners": (list,),
        "projects": (int,),
        "projects_limit": (int, type(None)),
    },
    "projects": {
        "key": _TEXT,
        "organization": _TEXT,
        "slot": _TEXT_OR_NULL,
        "profile": _TEXT_OR_NULL,
        "deleted_at": _TEXT_OR_NULL,
        "history": (list,),
    },
    "operations": {
        "id": _TEXT,
        "organization": _TEXT,
        "project_key": _TEXT_OR_NULL,
        "type": _TEXT,
        "status": _TEXT,
        "step": _TEXT_OR_NULL,
        "created_at": _TEXT,
        "started_at": _TEXT_OR_NULL,
    },
    "branches": {"project_key": _TEXT, "name": _TEXT, "state": _TEXT, "expires_at": _TEXT_OR_NULL},
    "slots": {"state": _TEXT, "slots": (int,)},
    "notifications": {"kind": _TEXT, "notifications": (int,)},
}

#: One operation of a project's history, as `control_states.project_state` reads it.
_HISTORY_SHAPE: dict[str, tuple[type, ...]] = {
    "type": _TEXT,
    "status": _TEXT,
    "error_code": _TEXT_OR_NULL,
    "created_at": _TEXT,
}

#: What `status` prints above each section.
STATUS_HEADINGS = {
    "organizations": "organisations",
    "projects": "projects",
    "operations": "operations pending or running",
    "branches": "branches",
    "slots": "slots",
    "notifications": "notifications in the last 24 hours",
}


def _shaped(rows: Any, shape: dict[str, tuple[type, ...]]) -> bool:
    return isinstance(rows, list) and all(
        isinstance(row, dict)
        and all(name in row and isinstance(row[name], kinds) for name, kinds in shape.items())
        for row in rows
    )


def read_section(container: str, database: str, name: str) -> tuple[list[Any] | None, str | None]:
    """One section's rows, or None and why it could not be read (ADR 0195)."""
    try:
        done = psql(container, database, STATUS_SECTIONS[name])
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"the cluster did not answer ({type(error).__name__})"
    if done.returncode != 0:
        return None, cluster_said(done)
    try:
        rows = json.loads(done.stdout.strip())
    except ValueError:
        rows = None
    shaped = _shaped(rows, STATUS_SHAPES[name])
    if shaped and name == "organizations":
        shaped = all(all(isinstance(o, str) for o in row["owners"]) for row in rows)
    if shaped and name == "projects":
        shaped = all(_shaped(row["history"], _HISTORY_SHAPE) for row in rows)
    if not shaped:
        return None, "the reading did not arrive in the shape asked for"
    return rows, None


def _project(row: dict[str, Any]) -> dict[str, Any]:
    state, managed_by = control_states.project_state(row["history"])
    last = row["history"][-1] if row["history"] else None
    return {
        "key": row["key"],
        "organization": row["organization"],
        "slot": row["slot"],
        "profile": row["profile"],
        "state": state,
        "managed_by": managed_by,
        "last_operation": None
        if last is None
        else {name: last[name] for name in ("type", "status", "created_at")},
    }


def status_sections(rows: dict[str, list[Any]]) -> dict[str, Any]:
    """Each section read, as `--json` carries it."""
    sections: dict[str, Any] = {}
    for name, read in rows.items():
        if name == "projects":
            sections[name] = {
                "listed": [_project(row) for row in read if row["deleted_at"] is None],
                "deleted": sum(1 for row in read if row["deleted_at"] is not None),
            }
        elif name == "slots":
            sections[name] = {row["state"]: row["slots"] for row in read}
        elif name == "notifications":
            sections[name] = {row["kind"]: row["notifications"] for row in read}
        else:
            sections[name] = read
    return sections


def _counted(counts: dict[str, int], nothing: str) -> str:
    return ", ".join(f"{name} {count}" for name, count in counts.items()) or nothing


def print_status(control: str, sections: dict[str, Any], unread: dict[str, str]) -> None:
    print(f"status of {control}")
    for name, heading in STATUS_HEADINGS.items():
        if name in unread:
            print(f"{heading} -- could not be read: {unread[name]}")
            continue
        value = sections[name]
        if name == "organizations":
            print(f"{heading} ({len(value)})")
            for o in value:
                limit = "no limit" if o["projects_limit"] is None else o["projects_limit"]
                owners = ", ".join(o["owners"]) or "none"
                print(
                    f"  {o['name']}  {o['plan']}  owners: {owners}"
                    f"  projects {o['projects']} of {limit}"
                )
        elif name == "projects":
            print(f"{heading} ({len(value['listed'])} listed, {value['deleted']} deleted)")
            for p in value["listed"]:
                state = p["state"]
                if p["managed_by"] == control_states.OPERATOR:
                    state += " (operator-managed)"
                last = p["last_operation"]
                said = (
                    "none"
                    if last is None
                    else f"{last['type']} {last['status']} {last['created_at']}"
                )
                print(
                    f"  {p['key']}  {p['organization']}  {p['slot'] or '-'}  {p['profile'] or '-'}"
                    f"  {state}  last: {said}"
                )
        elif name == "operations":
            print(f"{heading} ({len(value)})")
            for op in value:
                print(
                    f"  {op['created_at']}  {op['type']} {op['status']}"
                    f"  {op['project_key'] or '(no project yet)'}  {op['organization']}"
                )
        elif name == "branches":
            print(f"{heading} ({len(value)})")
            for b in value:
                print(
                    f"  {b['project_key']}/{b['name']}  {b['state']}"
                    f"  expires {b['expires_at'] or 'never'}"
                )
        else:
            print(heading)
            print(f"  {_counted(value, 'none recorded' if name == 'slots' else 'none')}")


def status(*, as_json: bool) -> int:
    require_root()
    control = find_control(read_all(), decision=False)
    container, database = target(control.document or {})
    rows: dict[str, list[Any]] = {}
    unread: dict[str, str] = {}
    for name in STATUS_SECTIONS:
        read, reason = read_section(container, database, name)
        if read is None:
            unread[name] = reason or "the reading did not arrive"
        else:
            rows[name] = read
    sections = status_sections(rows)
    if as_json:
        document: dict[str, Any] = {"control_project": control.key}
        for name in STATUS_SECTIONS:
            document[name] = {"unread": unread[name]} if name in unread else sections[name]
        print(json.dumps(document, indent=2))
    else:
        print_status(control.key, sections, unread)
    return EXIT_UNKNOWN if unread else EXIT_OK


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="control.sh", add_help=False)
    verbs = top.add_subparsers(dest="verb", required=True)
    adopt_verb = verbs.add_parser("adopt", add_help=False)
    adopt_verb.add_argument("--project", required=True)
    adopt_verb.add_argument("--organization", required=True)
    adopt_verb.add_argument("--confirm", required=True)
    registry_verb = verbs.add_parser("registry", add_help=False)
    registry_verb.add_argument("--json", action="store_true")
    status_verb = verbs.add_parser("status", add_help=False)
    status_verb.add_argument("--json", action="store_true")
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
        if arguments.verb == "status":
            return status(as_json=arguments.json)
        return totp_reset(arguments.username, confirm=arguments.confirm)
    except OperatorError as error:
        print(f"control: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
