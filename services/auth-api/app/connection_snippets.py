"""Connection snippets for a project's public doors (ADR 0268 item 6, D2352;
ADR 0295 decision 7, D2956, D2991).

`GET /v1/projects/{key}/connections` serves a project's recorded endpoints --
the deployed document's `database.public`, copied into the registry -- and
these: one text per client that was EXECUTED through the gateway, nothing for
a client nobody ran, and beside each a `where` line (which file, what to
install).

**The password is always the placeholder** `PASSWORD_PLACEHOLDER`. This plane
never holds a customer's password (ADR 0269): the customer's CLI generated it
into a file on their workstation, and only its SCRAM verifier ever left. A
snippet that could carry a value would be a second place a credential lives.

**Every text here runs** (Session 47 Run 6): `tests/contract/test_connection_
snippets.py` renders it through `snippets()` with a rig's doors, puts the rig's
password where the placeholder is, and runs it in its client's pinned image
against Traefik with the edge's `postgres` TLS option in front of the two
customer poolers started from `compose.yaml`'s own entrypoints (transaction
mode behind the pooled door, session mode behind the direct one), with
`verify-full` against a private CA installed where each client looks for its
roots -- and the same text pointed at a name the certificate does not carry
must fail. What each client needs, as measured there (rig 39c/39c2 before it):

* **psql / libpq** -- `sslmode=verify-full sslrootcert=system` (libpq 16 or
  newer reads `system`);
* **Prisma 6** -- `DATABASE_URL` on the pooled door, `DIRECT_URL` on the direct
  one (`migrate deploy` needs a session), `sslmode=require&sslaccept=strict`
  (which checks the host name: a misnamed door fails `hostname mismatch`), and
  **no `pgbouncer=true`**: the pooler keeps 100 prepared statements per
  connection. Prisma's CLI reads `.env`; Prisma Client does not, so the app
  loads it (`node --env-file=.env`);
* **node-postgres** -- `ssl: {rejectUnauthorized: true}`, Node's own roots;
* **psycopg 3** -- **not** `sslrootcert=system`: psycopg[binary] bundles an
  OpenSSL whose OPENSSLDIR is the directory it was built in
  (`/host/tmp/libpq.build`, 3.2.12 and 3.3.4), so `system` verifies against
  nothing on any machine; `sslrootcert=certifi.where()` does verify;
* **Drizzle** -- node-postgres underneath, the pooled door. Its own `migrate()`
  is refused on the direct door: it runs `CREATE SCHEMA IF NOT EXISTS` first,
  and the customer roles have no CREATE on the database (ADR 0269) -- so its
  migrations' SQL goes through the direct door with psql;
* **Go pgx v5** -- `sslmode=verify-full sslrootcert=system`, and the DEFAULT
  query mode (cached prepared statements) through the transaction pooler: no
  `default_query_exec_mode` is needed, because the pooler keeps them;
* **`.env`** -- two libpq URLs, read by psql and pgx. node-postgres reads
  `sslrootcert=system` as a file path (ENOENT) and psycopg[binary] as above, so
  the block names only the two that ran.

Standard library only: `src/agentic_postgres` loads this module through
`service_source.load` (ADR 0084) for its tests.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: What every snippet says where a password goes.
PASSWORD_PLACEHOLDER: Final = "<password from your file>"  # noqa: S105 -- the placeholder, never a value

#: The clients whose snippets were executed, in the order they are served.
CLIENTS: Final[tuple[str, ...]] = (
    "psql",
    "prisma",
    "node-pg",
    "psycopg",
    "drizzle",
    "go-pgx",
    "env",
)

#: Where each snippet goes and what to install, served beside it.
WHERE: Final[dict[str, dict[str, str]]] = {
    "psql": {
        "file": "your terminal",
        "install": "psql 16 or newer (it reads sslrootcert=system); "
        "the connecting page has a line for your operating system",
    },
    "prisma": {
        "file": '.env, beside prisma/schema.prisma (url = env("DATABASE_URL"), '
        'directUrl = env("DIRECT_URL")); the CLI reads it, your app loads it: '
        "node --env-file=.env",
        "install": "npm install prisma@6 @prisma/client@6",
    },
    "node-pg": {"file": "db.js", "install": "npm install pg"},
    "psycopg": {"file": "db.py", "install": 'pip install "psycopg[binary]" certifi'},
    "drizzle": {"file": "db.js", "install": "npm install drizzle-orm pg"},
    "go-pgx": {"file": "db.go", "install": "go get github.com/jackc/pgx/v5"},
    "env": {
        "file": ".env",
        "install": "nothing: psql 16+ and Go pgx read these URLs "
        "(node-postgres and psycopg[binary] do not read sslrootcert=system: use theirs)",
    },
}

_HOST = re.compile(r"(?=.{1,253}\Z)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}")


def _door(endpoint: Any) -> dict[str, Any]:
    """One door's members, each checked: a record that is not what a deploy
    writes yields no snippet rather than a snippet built from it."""
    if not isinstance(endpoint, dict):
        raise ValueError("an endpoint is not an object")
    host, port = endpoint.get("host"), endpoint.get("port")
    user, database = endpoint.get("user"), endpoint.get("database")
    if not isinstance(host, str) or not _HOST.fullmatch(host):
        raise ValueError("an endpoint's host is not a hostname")
    if not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536:
        raise ValueError("an endpoint's port is not a port")
    for value in (user, database):
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError("an endpoint's user or database is not an identifier")
    return {"host": host, "port": port, "user": user, "database": database}


def _url(door: dict[str, Any]) -> str:
    return (
        f"postgresql://{door['user']}:{PASSWORD_PLACEHOLDER}@{door['host']}:{door['port']}"
        f"/{door['database']}?sslmode=require&sslaccept=strict"
    )


def _libpq_url(door: dict[str, Any]) -> str:
    return (
        f"postgresql://{door['user']}:{PASSWORD_PLACEHOLDER}@{door['host']}:{door['port']}"
        f"/{door['database']}?sslmode=verify-full&sslrootcert=system"
    )


def _keywords(door: dict[str, Any]) -> str:
    return (
        f"host={door['host']} port={door['port']} user={door['user']} "
        f"dbname={door['database']} sslmode=verify-full"
    )


def _conninfo(door: dict[str, Any]) -> str:
    return f"{_keywords(door)} sslrootcert=system"


def _node_config(door: dict[str, Any], indent: str = "  ") -> tuple[str, ...]:
    return (
        f'{indent}host: "{door["host"]}",',
        f"{indent}port: {door['port']},",
        f'{indent}user: "{door["user"]}",',
        f'{indent}database: "{door["database"]}",',
        f'{indent}password: "{PASSWORD_PLACEHOLDER}",',
        f"{indent}ssl: {{ rejectUnauthorized: true }},",
    )


def snippets(endpoints: dict[str, Any]) -> dict[str, str]:
    """`{client: text}` for an enabled project's two doors, in `CLIENTS`'
    order; ValueError for a record that is not one."""
    if not isinstance(endpoints, dict) or endpoints.get("enabled") is not True:
        raise ValueError("the project has no public endpoints")
    pooled, direct = _door(endpoints.get("pooled")), _door(endpoints.get("direct"))
    return {
        "psql": "\n".join(
            (
                f"# Pooled (transaction mode), as {pooled['user']}:",
                f'psql "{_conninfo(pooled)}"',
                f"# Direct (a session: migrations, LISTEN, advisory locks), as {direct['user']}:",
                f'psql "{_conninfo(direct)}"',
            )
        ),
        "prisma": "\n".join(
            (
                f'DATABASE_URL="{_url(pooled)}"',
                f'DIRECT_URL="{_url(direct)}"',
            )
        ),
        "node-pg": "\n".join(
            (
                'import pg from "pg";',
                "",
                "const pool = new pg.Pool({",
                *_node_config(pooled),
                "});",
            )
        ),
        "psycopg": "\n".join(
            (
                "import certifi",
                "import psycopg",
                "",
                "conn = psycopg.connect(",
                f'    "{_keywords(pooled)} sslrootcert=" + certifi.where(),',
                f'    password="{PASSWORD_PLACEHOLDER}",',
                ")",
            )
        ),
        "drizzle": "\n".join(
            (
                "// db.js -- the pooled door (transaction mode)",
                'import pg from "pg";',
                'import { drizzle } from "drizzle-orm/node-postgres";',
                "",
                "export const pool = new pg.Pool({",
                *_node_config(pooled),
                "});",
                "export const db = drizzle(pool);",
                "",
                f"// Migrations: the direct door, as {direct['user']} -- run their SQL with the",
                "// psql snippet's second line. drizzle-orm's migrate() is refused there: it",
                "// runs CREATE SCHEMA first, and this project's roles may not create one.",
            )
        ),
        "go-pgx": "\n".join(
            (
                "// db.go",
                "package main",
                "",
                "import (",
                '\t"context"',
                "",
                '\t"github.com/jackc/pgx/v5"',
                '\t"github.com/jackc/pgx/v5/pgxpool"',
                ")",
                "",
                f"// connect opens the pooled door (transaction mode), as {pooled['user']}.",
                "func connect(ctx context.Context) (*pgxpool.Pool, error) {",
                f'\tconfig, err := pgxpool.ParseConfig("{_conninfo(pooled)}")',
                "\tif err != nil {",
                "\t\treturn nil, err",
                "\t}",
                f'\tconfig.ConnConfig.Password = "{PASSWORD_PLACEHOLDER}"',
                "\treturn pgxpool.NewWithConfig(ctx, config)",
                "}",
                "",
                "// connectDirect opens the direct door (a session: migrations, LISTEN,",
                f"// advisory locks), as {direct['user']}.",
                "func connectDirect(ctx context.Context) (*pgx.Conn, error) {",
                f'\tconfig, err := pgx.ParseConfig("{_conninfo(direct)}")',
                "\tif err != nil {",
                "\t\treturn nil, err",
                "\t}",
                f'\tconfig.Password = "{PASSWORD_PLACEHOLDER}"',
                "\treturn pgx.ConnectConfig(ctx, config)",
                "}",
            )
        ),
        "env": "\n".join(
            (
                "# DATABASE_URL: the pooled door (transaction mode), for the application.",
                "# DIRECT_URL: the direct door (a session), for migrations.",
                f'DATABASE_URL="{_libpq_url(pooled)}"',
                f'DIRECT_URL="{_libpq_url(direct)}"',
            )
        ),
    }


def where() -> dict[str, dict[str, str]]:
    """`{client: {file, install}}`, in `CLIENTS`' order -- a copy, so a caller
    that edits what it was handed edits nothing here."""
    return {client: dict(WHERE[client]) for client in CLIENTS}
