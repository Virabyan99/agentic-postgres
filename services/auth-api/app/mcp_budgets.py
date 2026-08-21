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


# ---------------------------------------------------------------------------
# the fifth bound: memory (ADR 0131)
# ---------------------------------------------------------------------------

#: What this process costs resident before it serves anything, in MiB.
#:
#: **Measured, and charged above the measurement.** ADR 0082's rig -- one fresh
#: interpreter per arm, because `ru_maxrss` is a high-water mark, and a control
#: that imports nothing and moves the figure by 0.0:
#:
#:     CONTROL -- nothing imported        12.1 MiB
#:     + jwt and cryptography             29.0
#:     + mcp.types                        54.3      <- the cost is HERE
#:     + fastmcp                          54.9      <- and not here
#:     + the agent plane's nine modules   69.2
#:
#: The protocol library costs 25 MiB and the server framework on top of it costs
#: 0.6, which is the opposite of the intuition and is why the table is in the
#: comment. 128 is charged against the measured 69.2 (1.85x) -- higher than ADR
#: 0082's 1.58x for the auth service, because that was a process the deployment
#: had been running for two sessions and **no `mcp` container has started
#: anywhere**. This is the interpreter, not the container.
PROCESS_OVERHEAD_MB = 128

#: What one concurrent read at the byte ceiling costs on top, in MiB.
#:
#: Measured through the real path -- socket bytes, `json.loads`, the byte budget,
#: `json.dumps` -- with N responses held live at once and a zero-read control:
#:
#:     CONTROL -- 0 reads   0.0 MiB
#:     1                    1.8
#:     2                    3.3
#:     5                    8.8
#:     10                  17.8
#:
#: Linear, at ~1.8 MiB for a 0.87 MiB response: roughly twice its own bytes,
#: because the parsed rows and the serialized string are both resident while it
#: is produced. **Deriving this from `MAX_SERIALIZED_BYTES` alone would have
#: understated it by that factor**, and nothing about the ceiling implies it.
PER_READ_MB = 4


def memory_floor_mb(max_concurrent_reads: int) -> int:
    """The smallest container limit that can hold that many reads at once.

    One function so the number in a comment, the number in a test and the number
    in `docs/` are one number -- ADR 0002's rule applied to arithmetic, and the
    reason `auth_memory_floor_mb` exists next door.

    **Nothing validates a manifest against this, deliberately** (ADR 0131).
    `api.rest.pool_size` is capped at 100 by the schema and the share is half of
    it, so the largest floor any valid document can ask for is 328 MiB against a
    limit of 384: a validator here could not fail. A guard that cannot go red is
    the defect this repository keeps producing, pointing the other way.
    """
    return PROCESS_OVERHEAD_MB + max_concurrent_reads * PER_READ_MB
