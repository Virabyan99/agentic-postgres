#!/usr/bin/env python3
"""Create the first administrator, once, locally.

**Why this is not an endpoint.** §4 lists four operations a re-run cannot undo,
and this is one of them: whoever the first administrator is decides who every
later one is. A public bootstrap route means the first caller to reach a freshly
deployed project becomes its administrator, and D230 is the record of refusing
to invent a deployment state to paper over that. So the first administrator is
created by a human at a terminal on the host, over the container-local
privileged socket, and `routes.app.status` stays `unavailable` until one exists.

**Four properties, and each one is a measurement rather than an intention.**

*Local.* The connection is `docker exec` into the project's own PostgreSQL
container. No TCP, no pooler, no network path at all. Measured, and it matters
for the third property: a session advisory lock taken through a transaction-mode
pooler is stranded on whichever backend ran the statement.

*Never an argument.* The password is read from a TTY, or from a file descriptor
the caller opened. It is never a parameter, never in the environment, and the
SQL that carries its hash goes to `psql` on **stdin** -- so `ps`, `/proc`, the
audit log and a shell history file all see the same thing, which is nothing.

*Exactly once.* `app_private.auth_bootstrap_administrator` takes a
project-scoped `pg_advisory_xact_lock` derived from `project_identity` before it
looks. Measured with a control: without the lock, two callers driven through the
interleaving by hand each read "no administrator" and each insert, and the table
ends with two.

*Recoverable without a second bootstrap.* If the output is lost, the documented
recovery is `auth-admin.sh list`, not another attempt. A second attempt is
refused (AP409) and the message says so.

Exit codes (runbook section 2 convention):
  0  the administrator was created, or state was listed
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployment or the database refused the operation
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import scope_registry  # noqa: E402

# `app.hashing` is deliberately NOT imported here (D292, ADR 0093).
#
# It imports `argon2` at module scope, and `argon2-cffi` exists in exactly one
# place in this system: the auth service's image, where its Dockerfile pins it.
# The host has no venv and its `python3` has no such package, so this import made
# the command unrunnable on the only machine it is ever run on --
# `ModuleNotFoundError: No module named 'argon2'`, on the first host bootstrap,
# after the deploy had otherwise succeeded.
#
# The screening and the hashing now happen INSIDE the auth container, and that is
# a better arrangement than the import would have been even had it worked: the
# hash an administrator is created with is produced by the very process that
# will later verify it, at the same argon2 build and the same frozen profile
# (ADR 0081). A hash computed here could differ from the service's, and the
# difference would surface as an administrator who cannot log in.

#: The role suffix an administrator holds. A constant rather than an option:
#: `--role` would let an operator bootstrap something that is not an
#: administrator, and the refusal check keys on this exact role.
ADMIN_ROLE_SUFFIX = "project_admin"

#: The Compose service whose image carries the hasher.
AUTH_SERVICE = "auth"

#: Screen and hash one password, inside the auth container.
#:
#: Reads the password from **stdin** and writes the PHC string to stdout. The
#: value is never an argument here for the same reason it is never one to this
#: command: argv is visible in `ps`, in `/proc/<pid>/cmdline` and to any audit
#: rule watching execve, and `docker exec`'s argv is the daemon's as well as
#: this process's.
#:
#: The forbidden list *is* passed as arguments, and that is not an oversight:
#: it holds the username and the project key, neither of which is a secret, and
#: both of which appear in the deployed document this command already reads.
#:
#: `sys.stdin.buffer.read().decode()` rather than `input()`: a password may end
#: in whitespace, and `input()` would strip the newline and nothing else while
#: `readline` would keep it. The caller sends exactly the bytes it read from the
#: terminal, and this decodes exactly those.
_HASH_PROGRAM = """
import sys
from app.hashing import Hasher, PasswordRejected, assess

password = sys.stdin.buffer.read().decode("utf-8")
try:
    screened = assess(password, forbidden=tuple(sys.argv[1:]))
except PasswordRejected as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(3) from None
sys.stdout.write(Hasher().hash(screened))
"""


class OperatorError(Exception):
    """Bad input from the person running this. Exit 2."""


class PrerequisiteError(Exception):
    """Something the host was supposed to provide. Exit 3."""


class DeploymentError(Exception):
    """The deployment or the database refused. Exit 5."""


def require_root() -> None:
    if os.geteuid() != 0:
        raise PrerequisiteError(
            "this command reaches the cluster over the container-local privileged "
            "socket and must be run as root, at a terminal"
        )


def load_outputs(path: Path) -> dict:
    if not path.is_file():
        raise OperatorError(f"deployed document not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    for key in ("database",):
        if key not in document:
            raise OperatorError(f"{path} is not a deployed document (no {key!r})")
    return document


def read_password(descriptor: int | None) -> str:
    """A TTY, or a file descriptor the caller opened. Never an argument.

    The confirmation prompt is not politeness. This value cannot be recovered
    and cannot be re-bootstrapped, so a typo here costs a redeployment; asking
    twice is the cheapest possible guard against the one mistake this command
    cannot undo.
    """
    if descriptor is not None:
        try:
            with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as handle:
                value = handle.readline()
        except OSError as exc:
            raise OperatorError(f"cannot read from file descriptor {descriptor}: {exc}") from exc
        # A trailing newline only. Stripping whitespace would silently change a
        # password whose first or last character is a space.
        return value.removesuffix("\n").removesuffix("\r")

    if not sys.stdin.isatty():
        raise OperatorError(
            "no terminal. Run this at a TTY, or pass --password-fd with a descriptor "
            "you opened -- the password is never an argument"
        )
    first = getpass.getpass("New administrator password: ")
    second = getpass.getpass("Repeat: ")
    if first != second:
        raise OperatorError("the two entries differ")
    return first


def psql(container: str, database: str, statement: str, *, stdin_sql: bool = True) -> str:
    """Run one statement in the project's container, over stdin.

    `-c` would put the statement in the argument vector, and the statement
    carries a password hash. `stdin` keeps it out of `ps`, `/proc/<pid>/cmdline`
    and anything reading either.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-qtA",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            database,
        ],
        input=statement if stdin_sql else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise DeploymentError(result.stderr.strip() or "psql failed with no message")
    return result.stdout.strip()


def quote_literal(value: str) -> str:
    """A SQL string literal, doubled quotes, no escapes.

    Used only for values this command produced or validated -- the username, the
    display name, the hash, the derived role name. It is not a general escaper
    and the backslash case is refused rather than handled, because a value
    needing `E''` syntax here would be a value nobody should be inserting.
    """
    if "\\" in value or "\x00" in value:
        raise OperatorError(f"value contains a backslash or a NUL and is refused: {value!r}")
    doubled = value.replace("'", "''")
    return f"'{doubled}'"


def auth_container(project_key: str) -> str:
    """The running auth container for this project, by Compose label.

    By label rather than by a derived name: the deployed document carries no
    per-service container name -- only `database.container` -- and ADR 0002 is
    explicit that a name is read rather than derived a second time. The labels
    are what Compose itself wrote.
    """
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project.working_dir=/var/lib/agentic-postgres/rendered/{project_key}",
            "--filter",
            f"label=com.docker.compose.service={AUTH_SERVICE}",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    names = [line for line in result.stdout.split() if line]
    if not names:
        raise PrerequisiteError(
            f"no running {AUTH_SERVICE!r} container for {project_key}. The bootstrap "
            "hashes the password with the service's own Argon2id build, so the service "
            "has to be up. Deploy through session 6 first, then bootstrap."
        )
    return names[0]


def screen_and_hash(*, project_key: str, password: str, forbidden: tuple[str, ...]) -> str:
    """Screen a password and return its Argon2id PHC string.

    Runs inside the auth container. The password goes over **stdin**; only the
    forbidden values -- the username and the project key, neither secret -- are
    arguments.

    `stderr` is forwarded on a refusal because `assess` explains what it refused
    and an operator at a terminal needs that. `stdout` is the hash and nothing
    else: no echo, no logging, no temporary file.
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            auth_container(project_key),
            "python",
            "-c",
            _HASH_PROGRAM,
            *[value for value in forbidden if value],
        ],
        input=password,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode == 3:
        raise OperatorError(result.stderr.strip() or "the password was refused")
    if result.returncode != 0:
        raise DeploymentError(
            f"the auth service could not hash the password (exit {result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )

    hashed = result.stdout
    if not hashed.startswith("$argon2id$"):
        raise DeploymentError(
            "the auth service returned something that is not an Argon2id hash. Nothing was written."
        )
    return hashed


def bootstrap(arguments: argparse.Namespace) -> int:
    require_root()
    document = load_outputs(Path(arguments.outputs))
    database = document["database"]
    container = database["container"]
    role_name = database["roles"][ADMIN_ROLE_SUFFIX]
    owner = database["roles"]["object_owner"]

    scopes = sorted(scope_registry.permitted_scopes(ADMIN_ROLE_SUFFIX))
    if not scopes:
        raise DeploymentError(f"the scope registry grants {ADMIN_ROLE_SUFFIX} nothing")

    password = read_password(arguments.password_fd)
    # Screened before it is hashed, with the project's own names refused --
    # `alpha-dev` is exactly what a person types when asked for a password they
    # will use once. Both happen in the auth container (D292).
    hashed = screen_and_hash(
        project_key=document.get("project", {}).get("key", ""),
        password=password,
        forbidden=(arguments.username, document.get("project", {}).get("key", "")),
    )

    literal_scopes = ", ".join(quote_literal(scope) for scope in scopes)
    statement = (
        f"SET ROLE {quote_identifier(owner)};\n"
        "SELECT app_private.auth_bootstrap_administrator("
        f"{quote_literal(arguments.username)}, "
        f"{quote_literal(arguments.display_name)}, "
        f"{quote_literal(role_name)}, "
        f"ARRAY[{literal_scopes}]::text[], "
        f"{quote_literal(hashed)});\n"
    )

    try:
        created = psql(container, database["name"], statement)
    except DeploymentError as exc:
        if "AP409" in str(exc):
            raise DeploymentError(
                "an active administrator already exists. If the first bootstrap's "
                "output was lost, inspect state with `bin/auth-admin.sh list` -- do "
                "not bootstrap again with a new password until the state is known"
            ) from exc
        raise

    print(f"administrator created: {created}")
    print(f"  username  {arguments.username}")
    print(f"  role      {role_name}")
    print(f"  scopes    {', '.join(scopes)}")
    print()
    print("The password was not printed and is not recoverable. If it is lost, use")
    print("the administrative API to set a new one; do not re-run this command.")
    return 0


def quote_identifier(value: str) -> str:
    """A SQL identifier. Refuses anything `naming.py` would never produce."""
    if not value or '"' in value or "\x00" in value:
        raise OperatorError(f"refusing to quote identifier {value!r}")
    return f'"{value}"'


def list_administrators(arguments: argparse.Namespace) -> int:
    """The documented recovery path, and the only one.

    Prints no verifier and no hash: `auth_list_users` returns neither, which is
    a property of the function rather than of this command remembering.
    """
    require_root()
    document = load_outputs(Path(arguments.outputs))
    database = document["database"]
    rows = psql(
        database["container"],
        database["name"],
        f"SET ROLE {quote_identifier(database['roles']['object_owner'])};\n"
        "SELECT username, role_name, status, authz_version, credential_version, "
        "coalesce(last_login_at::text, '-') FROM app_private.auth_list_users();\n",
    )
    if not rows:
        print("no subjects. This project has never been bootstrapped.")
        return 0
    print(f"{'username':24s} {'role':40s} {'status':10s} authz cred last_login")
    for line in rows.splitlines():
        name, role, status, authz, credential, last_login = line.split("|")
        print(f"{name:24s} {role:40s} {status:10s} {authz:>5s} {credential:>4s} {last_login}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auth-admin",
        description="Create the first administrator, once, locally.",
    )
    parser.add_argument("--outputs", required=True, help="the project's deployed outputs.json")
    subcommands = parser.add_subparsers(dest="command", required=True)

    create = subcommands.add_parser("bootstrap", help="create the first administrator")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", required=True)
    create.add_argument(
        "--password-fd",
        type=int,
        default=None,
        help=(
            "read the password from this already-open file descriptor instead of a "
            "terminal. There is deliberately no --password: an argument is visible in "
            "ps, /proc and the shell's history"
        ),
    )
    create.set_defaults(handler=bootstrap)

    listing = subcommands.add_parser("list", help="show subjects and their state")
    listing.set_defaults(handler=list_administrators)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return int(arguments.handler(arguments))
    except OperatorError as exc:
        print(f"auth-admin: {exc}", file=sys.stderr)
        return 2
    except PrerequisiteError as exc:
        print(f"auth-admin: {exc}", file=sys.stderr)
        return 3
    except DeploymentError as exc:
        print(f"auth-admin: {exc}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
