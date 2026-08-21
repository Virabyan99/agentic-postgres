"""The agent plane's concurrency bound, and where the other three live.

**Four budgets, four mechanisms, none derived from another** (ADR 0129). The
independence is the point, and it is easiest to see by asking what each one does
*not* bound:

    rows              `min(caller limit, resource.max_rows)`, in `mcp_query`
                      -- bounds how many rows, and nothing about their size
    serialized bytes  `MAX_SERIALIZED_BYTES`, in `mcp_tools`, checked after the
                      read -- bounds the answer, and nothing about the work
    elapsed time      `@server.tool(timeout=…)` from the lock's `timeout_ms`
                      -- measured: a 5 s body under a 1 s timeout returns at
                      1.10 s, against a 0.09 s control
    concurrency       here -- bounds how many callers are doing all of the above
                      at once, which none of the other three can express

**Why concurrency is bounded at all**, and it is not about this process. The
agent plane holds no database credential and takes no share of ADR 0099's
connection budget (D407). But every read it makes occupies one of **PostgREST's**
connections while it runs, and that pool is shared with human callers. An
unbounded agent plane cannot exhaust the cluster; it can exhaust the API.

Measured before this existed: eight overlapping tool calls ran **eight bodies at
once**. There was no bound of any kind.

**Saturation queues rather than refusing, and the time bound is what makes that
safe.** A caller arriving at a full semaphore waits; the tool's own timeout fires
if the wait is long. A queued request cannot outlive its budget -- which is the
clearest thing to point at when asked what "independently" buys.
"""

from __future__ import annotations

import asyncio
from typing import Any

#: How many upstream reads this process will have in flight at once.
#:
#: Rendered from `api.rest.pool_size` at half, floor one (ADR 0129), and handed
#: in rather than derived here: a runtime that computed its own share would be a
#: second authority for a division `config` owns, which is ADR 0070's rule and
#: D264's cost.
#:
#: **The ratio is a choice and this sentence is the flag.** Half leaves half the
#: pool for human callers under full agent load; nothing measures that half is
#: right. What is measured is that the two numbers must move together, and
#: deriving is what makes that true.
DEFAULT_MAX_CONCURRENT_READS = 5


class ReadSlots:
    """One semaphore, created with the event loop that will await it.

    Not a module-level `asyncio.Semaphore`: one built at import binds to
    whichever loop happens to be running then, and a second loop -- a test, a
    worker restart -- would await a primitive belonging to somebody else. Built
    lazily, inside the loop that uses it, for the same reason `AgentContext` is
    a `ContextVar` rather than a dict.
    """

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("a concurrency bound below one admits nothing")
        self._limit = limit
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def limit(self) -> int:
        return self._limit

    def _slots(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._limit)
        return self._semaphore

    async def __aenter__(self) -> Any:
        await self._slots().acquire()
        return self

    async def __aexit__(self, *_: Any) -> None:
        # Released in `__aexit__` rather than after the call, so a tool that
        # raises still gives its slot back. A semaphore leaked on the error path
        # is a bound that tightens every time something goes wrong, until the
        # plane stops answering for a reason nobody can see.
        self._slots().release()

    @property
    def available(self) -> int:
        """Slots not currently held. For telemetry and tests, never for a caller."""
        semaphore = self._semaphore
        return self._limit if semaphore is None else semaphore._value
