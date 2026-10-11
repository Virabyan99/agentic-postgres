"""Connection snippets for a project's public doors (ADR 0268 item 6, D2352).

`GET /v1/projects/{key}/connections` serves a project's recorded endpoints --
the deployed document's `database.public`, copied into the registry -- and
these: one text per client rig 39c connected through the gateway, nothing for
a client nobody measured.

**The password is always the placeholder** `PASSWORD_PLACEHOLDER`. This plane
never holds a customer's password (ADR 0269): the customer's CLI generated it
into a file on their workstation, and only its SCRAM verifier ever left. A
snippet that could carry a value would be a second place a credential lives.

What each client needs, as measured (ADR 0268, rig 39c/39c2):

* **psql / libpq** -- `sslmode=verify-full`, and `sslrootcert=system` for the
  public certificate authority the edge's resolver uses;
* **Prisma** -- `DATABASE_URL` on the pooled door, `DIRECT_URL` on the direct
  one (`migrate` needs a session), `sslmode=require&sslaccept=strict`, and **no
  `pgbouncer=true`**: the pooler keeps 100 prepared statements per connection;
* **node-postgres** -- a configuration object with `ssl: {rejectUnauthorized:
  true}`;
* **psycopg 3** -- a conninfo with `sslmode=verify-full sslrootcert=system`; its
  `cancel_safe()` cancels through the gateway and its legacy `cancel()` does
  not.

Standard library only: `src/agentic_postgres` loads this module through
`service_source.load` (ADR 0084) for its tests.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: What every snippet says where a password goes.
PASSWORD_PLACEHOLDER: Final = "<password from your file>"  # noqa: S105 -- the placeholder, never a value

#: The clients rig 39c measured, in the order they are served.
CLIENTS: Final[tuple[str, ...]] = ("psql", "prisma", "node-pg", "psycopg")

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


def _conninfo(door: dict[str, Any]) -> str:
    return (
        f"host={door['host']} port={door['port']} user={door['user']} "
        f"dbname={door['database']} sslmode=verify-full sslrootcert=system"
    )


def snippets(endpoints: dict[str, Any]) -> dict[str, str]:
    """`{client: text}` for an enabled project's two doors; ValueError for a
    record that is not one."""
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
                "const pool = new pg.Pool({",
                f'  host: "{pooled["host"]}",',
                f"  port: {pooled['port']},",
                f'  user: "{pooled["user"]}",',
                f'  database: "{pooled["database"]}",',
                f'  password: "{PASSWORD_PLACEHOLDER}",',
                "  ssl: { rejectUnauthorized: true },",
                "});",
            )
        ),
        "psycopg": f'psycopg.connect("{_conninfo(pooled)}", password="{PASSWORD_PLACEHOLDER}")',
    }
