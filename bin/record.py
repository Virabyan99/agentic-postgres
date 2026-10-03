#!/usr/bin/env python
"""The record a deployment keeps, and an operator's prune of it (ADR 0248, ADR 0213).

Invoked by ``bin/record.sh``, which is the documented entry point.

**This is ADR 0213's "human at a TTY" made a command, and nothing more.** It
reads ``app_private.record_size()`` and calls one of five prunes -- three from
migration 0039 (runs, deliveries, agents) and the two migration 0033 has shipped
since Session 28 (the agent audit and the idempotency claims) -- as the cluster's
superuser, through the database container, with the container and database read
from the project's DEPLOYED document (D1184) and never typed. Every prune is
granted to nobody in the database; root on the host is what reaches it.

**Nothing schedules it.** No unit, timer or other command calls this file, and
``tests/contract/test_record_command.py`` greps the tree for a caller.

The horizon is checked before anything is touched: an ISO 8601 instant WITH a
timezone (a naive time means a different moment on every host), and not in the
future. It reaches the database as a ``psql`` variable, never interpolated.
``--confirm`` must equal the project key, exactly.

Exit codes: 0 read or pruned; 2 invalid input; 3 not root, no deployed
document, or no docker; 5 the database refused the prune or the call failed;
6 the record could not be read -- reported, never folded into a zero (ADR 0195).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

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

#: `--what` -> the one function it calls, all in `app_private`, all taking
#: `(p_before timestamptz, p_limit integer)`. Exactly five, in one place.
PRUNES = {
    "runs": "workflow_run_prune",
    "deliveries": "connector_delivery_prune",
    "agents": "agent_prune",
    "audit": "agent_audit_prune",
    "idempotency": "agent_idempotency_prune",
}

#: A project key as `naming` derives one: what may be joined onto STATE_ROOT.
_KEY = re.compile(r"^[a-z][a-z0-9-]{0,62}$")

SIZE_QUERY = (
    "SELECT relation || '|' || row_count || '|' || coalesce(oldest::text, '') "
    "FROM app_private.record_size();"
)

#: How long one call may take. A prune of a large, never-pruned table is the
#: slow case; the bound exists so a hung cluster is reported, not waited on.
TIMEOUT_SECONDS = 600


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the deployed document is root-owned and the record is "
            "read through the database container as its superuser.",
        )


def parse_horizon(text: str, *, now: datetime | None = None) -> datetime:
    """An ISO 8601 instant with a timezone, not in the future. Before any connection."""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise OperatorError(EXIT_INPUT, f"--before is not an ISO 8601 time: {text!r}") from error
    if moment.tzinfo is None:
        raise OperatorError(
            EXIT_INPUT,
            "--before has no timezone; write one (2026-10-01T00:00:00Z or +00:00), "
            "because a naive time names a different instant on every host",
        )
    if moment > (now or datetime.now(UTC)):
        raise OperatorError(EXIT_INPUT, "--before is in the future; a horizon is in the past")
    return moment


def load_document(key: str) -> dict:
    if not _KEY.match(key):
        raise OperatorError(EXIT_INPUT, f"not a project key: {key!r}")
    path = deployed_output.deployed_path(key, root=STATE_ROOT)
    if not path.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"no deployed document for {key}: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_PREREQUISITE, f"{path} is not readable as JSON") from error
    return deployed_output.read_deployed_document(raw)


def target(document: dict) -> tuple[str, str]:
    database = document.get("database") or {}
    container, name = database.get("container"), database.get("name")
    if not container or not name:
        raise OperatorError(EXIT_PREREQUISITE, "the deployed document names no database container")
    return str(container), str(name)


def psql(container: str, database: str, sql: str, *variables: str):
    argv = ["psql", "-U", "postgres", "-d", database, "-X", "-qtA", "-v", "ON_ERROR_STOP=1"]
    for variable in variables:
        argv += ["-v", variable]
    return container_exec.run(container, *argv, "-f", "-", input=sql, timeout=TIMEOUT_SECONDS)


def read_size(container: str, database: str) -> list[dict]:
    """`record_size()`'s rows, or OperatorError(6) naming why it could not be read."""
    try:
        done = psql(container, database, SIZE_QUERY)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(EXIT_UNKNOWN, f"the record could not be read: {error}") from error
    if done.returncode != 0:
        reason = (done.stderr or "").strip().splitlines()
        raise OperatorError(
            EXIT_UNKNOWN,
            "the record could not be read: "
            + (reason[-1] if reason else "the cluster did not answer"),
        )
    rows = []
    for line in done.stdout.strip().splitlines():
        fields = line.split("|")
        if len(fields) != 3 or not fields[1].isdigit():
            raise OperatorError(
                EXIT_UNKNOWN,
                "the record could not be read: the reading did not arrive in the shape asked for",
            )
        rows.append({"relation": fields[0], "rows": int(fields[1]), "oldest": fields[2] or None})
    if not rows:
        raise OperatorError(EXIT_UNKNOWN, "the record could not be read: it returned no rows")
    return rows


def print_size(key: str, rows: list[dict], *, heading: str) -> None:
    print(f"record {key} -- {heading}")
    width = max(len(row["relation"]) for row in rows)
    for row in rows:
        print(f"  {row['relation']:<{width}}  {row['rows']:>9}  {row['oldest'] or '-'}")


def size(key: str, *, as_json: bool) -> int:
    require_root()
    container, database = target(load_document(key))
    rows = read_size(container, database)
    if as_json:
        print(json.dumps({"project": key, "relations": rows}, indent=2, sort_keys=True))
    else:
        print_size(key, rows, heading="now")
    return EXIT_OK


def prune(key: str, *, what: str, before: str, limit: int | None, confirm: str) -> int:
    # Everything an operator typed is checked before root, before the document,
    # and before any container is touched.
    if what not in PRUNES:
        raise OperatorError(EXIT_INPUT, f"--what is one of {', '.join(PRUNES)}")
    horizon = parse_horizon(before)
    if limit is not None and limit < 1:
        raise OperatorError(EXIT_INPUT, "--limit is a positive number of rows")
    if confirm != key:
        raise OperatorError(
            EXIT_INPUT, f"--confirm must be the project key exactly ({key}); nothing was pruned"
        )

    require_root()
    container, database = target(load_document(key))
    print_size(key, read_size(container, database), heading="before")

    function = PRUNES[what]
    bound = "NULL" if limit is None else str(int(limit))
    sql = f"SELECT app_private.{function}(:'before'::timestamptz, {bound});"
    try:
        done = psql(container, database, sql, f"before={horizon.isoformat()}")
    except (OSError, subprocess.TimeoutExpired) as error:
        # Whether the prune committed is not known: say so, and say how to find out.
        raise OperatorError(
            EXIT_UNKNOWN,
            f"{function} did not answer ({type(error).__name__}); whether it removed "
            f"anything is not known -- read `record.sh size --project {key}`",
        ) from error
    if done.returncode != 0:
        for line in (done.stderr or "").strip().splitlines():
            print(line, file=sys.stderr)
        print(
            f"record: {function} did not run to completion; nothing was removed by it",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    removed = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else "?"
    print(
        f"record {key} -- {function}(before {horizon.isoformat()}, limit {bound}) removed {removed}"
    )

    try:
        print_size(key, read_size(container, database), heading="after")
    except OperatorError as error:
        # The prune committed; only the second reading failed. Said, not folded.
        print(f"record: {error}", file=sys.stderr)
        return EXIT_UNKNOWN
    return EXIT_OK


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="record.sh", add_help=False)
    verbs = top.add_subparsers(dest="verb", required=True)
    size_verb = verbs.add_parser("size", add_help=False)
    size_verb.add_argument("--project", required=True)
    size_verb.add_argument("--json", action="store_true")
    prune_verb = verbs.add_parser("prune", add_help=False)
    prune_verb.add_argument("--project", required=True)
    prune_verb.add_argument("--what", required=True)
    prune_verb.add_argument("--before", required=True)
    prune_verb.add_argument("--limit", type=int)
    prune_verb.add_argument("--confirm", required=True)
    return top


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
    except SystemExit:
        return EXIT_INPUT
    try:
        if arguments.verb == "size":
            return size(arguments.project, as_json=arguments.json)
        return prune(
            arguments.project,
            what=arguments.what,
            before=arguments.before,
            limit=arguments.limit,
            confirm=arguments.confirm,
        )
    except OperatorError as error:
        print(f"record: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    raise SystemExit(main())
