"""The connection pool, opened by the lifespan and by nothing else.

**`open=False` is not a style choice.** Measured in Run 7 against psycopg-pool
3.3.1: the `open` parameter defaults to `None`, and a pool constructed at import
time with the default begins connecting as soon as it exists -- before the
application has decided it is ready, and with no place to report a failure
except a background task that logs and retries. Constructed with `open=False`
against a conninfo pointing at a closed port, nothing was attempted; `open()`
then raised `PoolTimeout` where the caller could see it, and `close()` returned
cleanly.

That is the whole property this module exists to hold: **the process decides
when it connects, and a failure to connect is a startup failure rather than a
service that is up and answering 500s.**

**The pool's size is not this file's to choose.** `api.app.pool_size` is
declared in the manifest, charged to the cluster's connection budget by
`config.auth_connection_budget`, published in the deployed document as
`database.auth_connection_budget` and read from the environment here. Four
places, one number, and the direction of travel is one way (ADR 0070).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Final

from psycopg_pool import AsyncConnectionPool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

#: How long `open()` will wait for the pool to reach `min_size` before failing
#: the start. Bounded, and short enough that a container held by a cluster that
#: is not coming back is restarted by Compose rather than sitting in a
#: half-started state that its healthcheck cannot describe.
OPEN_TIMEOUT_SECONDS: Final = 15.0

#: How long a request will wait for a connection before giving up. Separate
#: from the open timeout because they answer different questions: this one is
#: "the pool is busy", that one is "the cluster is not there".
ACQUIRE_TIMEOUT_SECONDS: Final = 5.0

#: Recycled well before PgBouncer's own `server_lifetime`, so a connection is
#: retired by the side that can do it between requests rather than by the
#: pooler underneath an in-flight one.
MAX_LIFETIME_SECONDS: Final = 1800.0

#: Session-scoped settings applied to every connection the pool hands out, as
#: SQL rather than as conninfo options: `options=-c ...` in a conninfo is a
#: second place connection parameters are configured, and PgBouncer in
#: transaction mode does not carry it across a server change.
#:
#: `statement_timeout` is the service's own bound and is deliberately shorter
#: than anything the pooler enforces. `idle_in_transaction_session_timeout`
#: closes the failure mode where a cancelled request leaves a transaction open
#: holding a connection the budget has already been spent on.
SESSION_SETTINGS: Final = (
    "SET statement_timeout = '5s'",
    "SET idle_in_transaction_session_timeout = '10s'",
    "SET lock_timeout = '2s'",
    # The service reaches app_private through functions and holds no objects of
    # its own. An empty search_path means every reference is schema-qualified,
    # which is what makes a function resolvable by exactly one name.
    "SET search_path = ''",
)


async def _configure(connection: Any) -> None:
    """Applied to each connection as the pool creates it."""
    for statement in SESSION_SETTINGS:
        await connection.execute(statement)
    await connection.commit()


def build_pool(conninfo: str, *, size: int, name: str = "auth") -> AsyncConnectionPool:
    """Construct a closed pool. Nothing here connects.

    `min_size` equals `max_size` deliberately. A pool that grows on demand
    takes its connections from the cluster at the moment of highest load, which
    is the moment the budget has least slack; taking them at startup means a
    project whose arithmetic is wrong fails to start rather than failing to log
    somebody in an hour later.
    """
    if size < 1:
        raise ValueError("pool size must be at least 1")
    return AsyncConnectionPool(
        conninfo,
        min_size=size,
        max_size=size,
        name=name,
        open=False,
        timeout=ACQUIRE_TIMEOUT_SECONDS,
        max_lifetime=MAX_LIFETIME_SECONDS,
        configure=_configure,
        # Every connection is checked before it is handed out. The cost is one
        # round trip; the alternative is a request that fails because it was
        # given a connection the pooler had already closed.
        check=AsyncConnectionPool.check_connection,
    )


@asynccontextmanager
async def pool_lifespan(pool: AsyncConnectionPool) -> AsyncIterator[AsyncConnectionPool]:
    """Open on entry, close on exit, and fail loudly on either.

    `wait=True` with a bounded timeout: the context does not yield until the
    pool actually holds `min_size` connections, so a caller inside the `with`
    can assume a working pool rather than checking. An unreachable cluster
    raises here, at startup, which is where a deployment problem belongs.
    """
    await pool.open(wait=True, timeout=OPEN_TIMEOUT_SECONDS)
    try:
        yield pool
    finally:
        # In a `finally` so that a failure anywhere inside the application's
        # lifetime still returns the connections. A container that exits
        # holding its share of the budget leaves the cluster short until the
        # backends time out.
        await pool.close()
