#!/usr/bin/env python
"""The customer poolers' userlists, regenerated from `pg_authid` (ADR 0269 item 5).

Invoked by ``bin/customer-credentials.sh``, which is the documented entry point.

One verb, ``sync --outputs FILE``. It reads both customer roles' SCRAM
verifiers out of the project's cluster -- as the cluster's superuser, through
the database container (``container_exec.run``), with the container, the
database and the two role names read from the outputs document (ADR 0002) and
never typed -- writes one userlist per pooler under
``/etc/agentic-postgres/projects/<key>/customer-poolers/`` (``root:70``, 0750
directory, 0640 files, written beside and renamed), and SIGHUPs both poolers so
they re-read it (rig 5a: a directory bind sees the renamed file).

**It never prints a verifier**, and never handles a password: none exists on
the host (ADR 0269). The control plane's `credential.rotate` sets the verifier
and calls this; a deploy calls it at step 6f, so a restore or a branch -- which
carry `pg_authid` with the data -- carries the customer's credential too.

A document whose project has no public endpoints is not an error: nothing is
written and the command says so, exit 0.

Exit codes: 0 synced, or nothing to sync; 2 invalid input; 3 not root, no
document, or no docker; 6 the cluster could not be read or a pooler could not be
signalled -- reported, never folded into success (ADR 0195). On 6 after the
files were written, the line says which pooler still serves the old list.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import (  # noqa: E402
    container_exec,
    customer_credentials,
    deployed_output,
    naming,
    runtime_override,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_UNKNOWN = 6

#: Where the userlists live; a proof points it at a directory it owns.
STATE_ROOT = deployed_output.PROJECT_STATE_ROOT

#: A read of two rows and a signal: a bound so a hung cluster is reported.
TIMEOUT_SECONDS = 60


class OperatorError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_root() -> None:
    if os.geteuid() != 0:
        raise OperatorError(
            EXIT_PREREQUISITE,
            "must run as root: the userlists are root-owned, the verifiers are read "
            "through the database container as its superuser, and the poolers are "
            "signalled through Docker.",
        )


def load_document(path: Path) -> dict:
    if not path.is_file():
        raise OperatorError(EXIT_PREREQUISITE, f"outputs document not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise OperatorError(EXIT_PREREQUISITE, f"{path} is not readable as JSON") from error
    if not isinstance(document, dict) or "database" not in document:
        raise OperatorError(EXIT_PREREQUISITE, f"{path} is not an outputs document")
    return document


def doors(document: dict) -> dict[str, str] | None:
    """`{service: role}` for the two customer poolers, or None when the project
    has no public endpoints (or its document predates them, outputs < 22)."""
    public = (document.get("database") or {}).get("public") or {}
    if not public.get("enabled"):
        return None
    pooled, direct = public.get("pooled") or {}, public.get("direct") or {}
    if not pooled.get("user") or not direct.get("user"):
        raise OperatorError(
            EXIT_PREREQUISITE, "the document enables public endpoints and names no customer role"
        )
    return {
        naming.CUSTOMER_POOL_SERVICE: str(pooled["user"]),
        naming.CUSTOMER_DIRECT_SERVICE: str(direct["user"]),
    }


def read_verifiers(document: dict, roles: dict[str, str]) -> dict[str, str | None]:
    database = document["database"]
    container, name = database.get("container"), database.get("name")
    if not container or not name:
        raise OperatorError(EXIT_PREREQUISITE, "the document names no database container")
    argv = [
        "psql", "-U", "postgres", "-d", str(name), "-X", "-qtA", "-v", "ON_ERROR_STOP=1",
        "-v", f"pool_role={roles[naming.CUSTOMER_POOL_SERVICE]}",
        "-v", f"direct_role={roles[naming.CUSTOMER_DIRECT_SERVICE]}",
        "-f", "-",
    ]  # fmt: skip
    try:
        done = container_exec.run(
            str(container),
            *argv,
            input=customer_credentials.VERIFIER_QUERY,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OperatorError(EXIT_UNKNOWN, f"the cluster could not be read: {error}") from error
    if done.returncode != 0:
        # psql's stderr names the failure (a stopped container, a refused
        # login); it cannot contain a verifier, which only stdout carries.
        raise OperatorError(
            EXIT_UNKNOWN, f"the cluster could not be read: {done.stderr.strip()[:300]}"
        )
    try:
        return customer_credentials.parse_verifiers(done.stdout, tuple(roles.values()))
    except customer_credentials.CredentialError as error:
        raise OperatorError(EXIT_UNKNOWN, str(error)) from error


def signal(container: str) -> str | None:
    """SIGHUP one pooler; None on success, else why not."""
    try:
        done = subprocess.run(
            ["docker", "kill", "--signal", "HUP", container],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    return None if done.returncode == 0 else (done.stderr.strip() or f"exit {done.returncode}")


def command_sync(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_document(Path(arguments.outputs))
    key = str((document.get("project") or {}).get("key") or "")
    if not key:
        raise OperatorError(EXIT_PREREQUISITE, "the document names no project key")
    roles = doors(document)
    if roles is None:
        print(f"customer-credentials: {key} has no public endpoints; nothing to sync")
        return EXIT_OK

    verifiers = read_verifiers(document, roles)

    directory = customer_credentials.userlist_directory(key, root=STATE_ROOT)
    customer_credentials.ensure_directory(directory)
    for service, role in roles.items():
        filename = runtime_override.CUSTOMER_USERLISTS[service]
        text = customer_credentials.userlist(role, verifiers[role])
        customer_credentials.write_userlist(directory, filename, text)
        state = "credential set" if verifiers[role] else "no credential yet (refuses every login)"
        print(f"  {filename}: {role}: {state}")

    unsignalled = []
    for container in naming.customer_pooler_containers(key):
        problem = signal(container)
        if problem is not None:
            unsignalled.append(f"{container}: {problem}")
    if unsignalled:
        raise OperatorError(
            EXIT_UNKNOWN,
            "the userlists are written, and these poolers were not told to re-read "
            "them (each still serves its previous list until it restarts): "
            + "; ".join(unsignalled),
        )
    print(f"customer-credentials: {key}: both poolers re-read their userlists")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="customer-credentials.sh")
    verbs = parser.add_subparsers(dest="verb", required=True)
    sync = verbs.add_parser("sync")
    sync.add_argument("--outputs", required=True)
    sync.set_defaults(handler=command_sync)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
    except SystemExit as exit_:
        return EXIT_INPUT if exit_.code not in (0, None) else EXIT_OK
    try:
        return arguments.handler(arguments)
    except OperatorError as error:
        print(f"customer-credentials: {error}", file=sys.stderr)
        return error.code


if __name__ == "__main__":
    sys.exit(main())
