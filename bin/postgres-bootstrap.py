#!/usr/bin/env python3
"""The bootstrap plane's SQL, generated and executed over the container socket.

Invoked only by ``bin/postgres-bootstrap.sh``, which owns the operator surface
and the privilege gate. Split out for the same reason
``bin/bootstrap-providers.py`` is: the shell script is the contract and the
Python is the work, and building SQL in bash is how quoting mistakes become
injection.

**Statements are generated here and never taken from a file.** Every identifier
comes from the rendered ``outputs.json``, which is the single authority for
derived names, and is quoted through ``migrations.quote_identifier`` -- the same
function the migration renderer uses, so an identifier that would be refused
there is refused here. There is no path that takes SQL from an argument, from
stdin, or from a manifest.

**What it deliberately does not do.** It applies no migration, and it removes
nothing. A volume whose recorded identity does not match stops the run with
exit 11 and is never adopted (ADR 0030).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import migrations

EXIT_CONTRACT = 5
EXIT_CHECK_FAILED = 6
EXIT_UNREACHABLE = 9
EXIT_IDENTITY_MISMATCH = 11

#: Compared on a mismatch. Deliberately only the immutable fields: the source
#: commit, manifest checksum and template version all change on a legitimate
#: redeploy, and a check that fires on a valid volume is one operators learn to
#: override (ADR 0030).
IDENTITY_FIELDS = ("project_key", "database_name", "compose_project_name", "instance_uuid")


def psql(container: str, database: str, sql: str, *, read_only: bool = False) -> str:
    """Run SQL over the container's Unix socket as the OS postgres user.

    `docker exec -i`, and the `-i` is load-bearing: without it stdin is not
    forwarded, psql reads nothing, and the command exits 0 having executed
    nothing at all. That failure is silent and looks exactly like success.
    """
    command = ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", database, "-X"]
    command += ["-v", "ON_ERROR_STOP=1", "-qtA"]
    if read_only:
        command += ["-c", sql]
        stdin = None
    else:
        stdin = sql
        command += ["-f", "-"]

    result = subprocess.run(
        command, input=stdin, capture_output=True, text=True, check=False, timeout=300
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()
        raise SystemExit(
            f"postgres-bootstrap: the cluster refused a statement: "
            f"{message[0] if message else 'no output'}"
        )
    return result.stdout.strip()


def query(container: str, database: str, sql: str) -> str:
    return psql(container, database, sql, read_only=True)


def build_statements(document: dict[str, Any], instance_uuid: str) -> list[str]:
    """Every statement the bootstrap plane issues, in order.

    Returned as a list rather than executed inline so that ``--check`` can
    report what would run without a second code path deciding what that is.
    """
    database = document["database"]
    roles = database["roles"]
    q = migrations.quote_identifier
    db = q(database["name"])

    statements: list[str] = []

    # The thirteen roles. NOLOGIN and NOINHERIT, with a null password verifier:
    # migration_user is the only one Session 3 activates, and it is activated by
    # the secret flow rather than here. Bootstrap clears an unexpected verifier
    # rather than tolerating it -- a role that acquired a password outside the
    # generation flow is a credential nobody can rotate.
    for name in roles.values():
        # S608 is suppressed here and at the sentinel INSERT below, and only
        # there. Every interpolated value is a derived identity from
        # outputs.json passed through `quote_identifier` or `quote_literal`,
        # which validate before quoting and raise on anything that is not
        # already a bare lowercase identifier or a plain string -- so a value
        # that could change the statement's shape never reaches the f-string.
        # Parameter binding is not available: PostgreSQL does not accept a
        # parameter where an identifier goes, which is the whole reason
        # `quote_identifier` exists.
        literal = migrations.quote_literal(name)
        create_role = (
            "DO $$ BEGIN "  # noqa: S608
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {literal}) "
            f"THEN CREATE ROLE {q(name)} NOLOGIN NOINHERIT; END IF; END $$;"
        )
        statements.append(create_role)
        statements.append(
            f"ALTER ROLE {q(name)} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
        )

    # The migration plane reaches owner authority only by assuming it: SET TRUE
    # so it can, INHERIT FALSE so it does not hold it merely by connecting,
    # ADMIN FALSE so it cannot grant the membership onward. The catalog tests
    # read these three columns directly; inferring them from the role's own
    # rolinherit would pass for the wrong reason (ADR 0026).
    statements.append(
        f"GRANT {q(roles['object_owner'])} TO {q(roles['migration_user'])} "
        f"WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;"
    )

    # Database-level posture. PUBLIC loses everything first, so a grant below is
    # the only way any role holds anything.
    statements.append(f"REVOKE ALL ON DATABASE {db} FROM PUBLIC;")
    statements.append(
        f"GRANT CREATE, CONNECT, TEMPORARY ON DATABASE {db} TO {q(roles['object_owner'])};"
    )
    statements.append(
        f"GRANT CONNECT ON DATABASE {db} TO "
        f"{q(roles['migration_user'])}, {q(roles['app_runtime'])};"
    )

    # Superuser work, and the reason this plane exists. pgvector is untrusted,
    # so CREATE EXTENSION requires superuser -- measured, not assumed. The
    # schema is created AUTHORIZATION the owner so that a later migration can
    # GRANT USAGE on it without needing this authority again.
    statements.append(
        f"CREATE SCHEMA IF NOT EXISTS extensions AUTHORIZATION {q(roles['object_owner'])};"
    )
    statements.append("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;")

    # app_private has to exist before the sentinel can live in it, and the
    # sentinel has to exist before any migration runs -- so neither can wait for
    # migration 0002. Creating it here idempotently means 0002 finds it present.
    statements.append(
        f"CREATE SCHEMA IF NOT EXISTS app_private AUTHORIZATION {q(roles['object_owner'])};"
    )
    statements.append(
        "CREATE TABLE IF NOT EXISTS app_private.project_identity ("
        "singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton), "
        "project_key text NOT NULL, database_name text NOT NULL, "
        "compose_project_name text NOT NULL, instance_uuid uuid NOT NULL, "
        "bound_at timestamptz NOT NULL DEFAULT now());"
    )
    # Same rule as the role loop above: every value is quoted through
    # `quote_literal`, which raises on anything that is not a plain string.
    identity_values = ", ".join(
        migrations.quote_literal(value)
        for value in (
            document["project"]["key"],
            database["name"],
            document["compose"]["project_name"],
            instance_uuid,
        )
    )
    bind_identity = (
        "INSERT INTO app_private.project_identity "  # noqa: S608
        "(project_key, database_name, compose_project_name, instance_uuid) "
        f"VALUES ({identity_values}) ON CONFLICT (singleton) DO NOTHING;"
    )
    statements.append(bind_identity)
    return statements


def read_identity(container: str, database: str) -> dict[str, str] | None:
    """The sentinel row, or None if the table does not exist yet."""
    exists = query(
        container,
        database,
        "SELECT to_regclass('app_private.project_identity') IS NOT NULL;",
    )
    if exists != "t":
        return None
    row = query(
        container,
        database,
        "SELECT project_key || '|' || database_name || '|' || compose_project_name "
        "|| '|' || instance_uuid FROM app_private.project_identity;",
    )
    if not row:
        return None
    return dict(zip(IDENTITY_FIELDS, row.split("|"), strict=True))


def assert_identity_matches(observed: dict[str, str], document: dict[str, Any]) -> None:
    expected = {
        "project_key": document["project"]["key"],
        "database_name": document["database"]["name"],
        "compose_project_name": document["compose"]["project_name"],
    }
    differing = [
        f"{field}: expected {expected[field]!r}, volume says {observed[field]!r}"
        for field in expected
        if observed[field] != expected[field]
    ]
    if differing:
        # No secret is printed: every field compared is a derived, non-secret
        # identity. The instance UUID is reported because it is what an operator
        # matches against a volume, and it identifies nothing on its own.
        print("postgres-bootstrap: this volume belongs to a different project.", file=sys.stderr)
        for line in differing:
            print(f"  {line}", file=sys.stderr)
        print(f"  volume instance_uuid: {observed['instance_uuid']}", file=sys.stderr)
        print(
            "  Nothing was changed. Bootstrap never adopts a volume: select the correct "
            "one, or write a reviewed migration plan.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_IDENTITY_MISMATCH)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--mode", choices=("check", "apply"), default="check")
    parser.add_argument("--state-root", required=True)
    arguments = parser.parse_args()

    document = json.loads(Path(arguments.outputs).read_text(encoding="utf-8"))
    container = document["database"]["container"]
    database = document["database"]["name"]

    if (
        subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        != "true"
    ):
        print(
            f"postgres-bootstrap: the container {container} is not running; "
            "the cluster cannot be reached.",
            file=sys.stderr,
        )
        return EXIT_UNREACHABLE

    observed = read_identity(container, database)
    if observed is not None:
        assert_identity_matches(observed, document)

    # A candidate UUID is generated only when the sentinel does not exist. On a
    # non-empty volume the committed row is authoritative and is recovered, never
    # regenerated -- a fresh UUID against existing data is how a volume stops
    # matching itself (ADR 0030).
    instance_uuid = observed["instance_uuid"] if observed else str(uuid.uuid4())

    statements = build_statements(document, instance_uuid)

    if arguments.mode == "check":
        print(f"postgres-bootstrap: --check, {len(statements)} statements would run")
        print(f"  container      {container}")
        print(f"  database       {database}")
        print(f"  identity       {'bound' if observed else 'not yet bound'}")
        print(f"  roles declared {len(document['database']['roles'])}")
        return 0

    psql(container, database, "\n".join(statements))
    print(f"postgres-bootstrap: {len(statements)} statements applied to {database}")
    print(f"  identity {instance_uuid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
