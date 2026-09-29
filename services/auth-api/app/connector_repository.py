"""The connector calls: eight of migration 0036's definer functions.

`auth_service` holds **no privilege of any kind on the four connector tables**
(0036, and `test_connectivity_substrate.py::test_the_four_tables_grant_nothing_
to_any_role`). Everything below goes through a `SECURITY DEFINER` function, the
shape `workflow_repository.py` states for the workflow tables: there is no
statement this role could issue that moves a delivery it does not hold, enables a
connector for an agent whose scopes differ, or reads an endpoint outside the one
claim that returns it.

**Four 0036 functions are deliberately absent.** `app.emit_event` is granted to
nobody and called only by a definer function running as the object owner (ADR
0235); `connector_install` is the deploy's step 6e and
`connector_rehearse_delivery` the rehearsal's, both as the bootstrap superuser
(ADR 0236, ADR 0238); `connector_scopes_match` is called only by the functions
here. A reader looking for them finds this paragraph instead of a gap.

**The ninth granted function, `workflow_await_event`, is a step's** and lives
on `WorkflowRepository` beside `park`, whose attempt row it writes.

**Each method is one autocommit round trip and holds nothing open**, for ADR
0104's reason: the delivery's POST happens between `claim_delivery` and
`finish_delivery`, never inside either, and the lease -- not a row lock -- is
what survives the gap (ADR 0238).

**This module ships with the grants, in Run 3, for D1680's reason**:
`test_every_granted_function_has_a_caller` refuses a grant no code calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True, slots=True)
class ClaimedDelivery:
    """One leased delivery: what to send, and to where, for ONE attempt.

    `endpoint` is `None` for a rehearsal's delivery, which the worker sends to
    the container's discard port instead (ADR 0238). It is held in memory for
    the attempt and written nowhere: not a log line, not an error, not a row.
    """

    delivery_id: UUID
    connector_name: str
    endpoint: str | None
    rehearsal: bool
    event_id: UUID
    event_name: str
    event_version: int
    emitted_at: datetime
    payload: dict[str, Any]
    attempt: int
    max_attempts: int


class ConnectorRepository:
    """The connectors, as the auth service's own role sees them."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def _one(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(statement, parameters)
            return await cursor.fetchone()

    async def claim_delivery(self, *, holder: str, lease_seconds: int) -> ClaimedDelivery | None:
        """Lease at most one due delivery. `None` means there is nothing to send."""
        row = await self._one(
            "SELECT * FROM app_private.connector_claim_delivery(%s, %s)",
            (holder, lease_seconds),
        )
        if row is None:
            return None
        return ClaimedDelivery(
            delivery_id=row["delivery_id"],
            connector_name=str(row["connector_name"]),
            endpoint=row["endpoint"],
            rehearsal=bool(row["rehearsal"]),
            event_id=row["event_id"],
            event_name=str(row["event_name"]),
            event_version=int(row["event_version"]),
            emitted_at=row["emitted_at"],
            payload=dict(row["payload"]),
            attempt=int(row["attempt"]),
            max_attempts=int(row["max_attempts"]),
        )

    async def finish_delivery(
        self,
        *,
        delivery_id: UUID,
        holder: str,
        delivered: bool,
        status: int | None,
        error: str | None,
    ) -> str:
        """Record one attempt: `delivered`, `pending` again, `dead`, or `lease_lost`."""
        row = await self._one(
            "SELECT app_private.connector_finish_delivery(%s, %s, %s, %s, %s) AS status",
            (delivery_id, holder, delivered, status, error),
        )
        assert row is not None
        return str(row["status"])

    async def fire_due(self) -> int:
        """Enqueue one run per due scheduled connector; the number enqueued."""
        row = await self._one("SELECT app_private.connector_fire_due() AS fired", ())
        assert row is not None
        return int(row["fired"])

    async def inbound(self, *, name: str) -> dict[str, Any]:
        """An inbound connector's id and body declaration -- read AFTER the signature."""
        row = await self._one("SELECT app_private.connector_inbound(%s) AS connector", (name,))
        assert row is not None
        return dict(row["connector"])

    async def accept(self, *, name: str, delivery_id: UUID, body: dict[str, Any]) -> UUID:
        """Accept one delivery exactly once and start its run; the run's id."""
        row = await self._one(
            "SELECT app_private.connector_accept(%s, %s, %s::jsonb) AS run_id",
            (name, delivery_id, _json(body)),
        )
        assert row is not None
        return UUID(str(row["run_id"]))

    async def enable(self, *, name: str, agent_id: UUID | None, user_id: UUID) -> str:
        """An administrator's enable (ADR 0236). Refusals arrive as the function's tokens."""
        row = await self._one(
            "SELECT app_private.connector_enable(%s, %s, %s) AS outcome",
            (name, agent_id, user_id),
        )
        assert row is not None
        return str(row["outcome"])

    async def disable(self, *, name: str, user_id: UUID | None) -> str:
        """An administrator's disable; pending deliveries are held, not sent."""
        row = await self._one(
            "SELECT app_private.connector_disable(%s, %s) AS outcome", (name, user_id)
        )
        assert row is not None
        return str(row["outcome"])

    async def status(self, *, dead_limit: int) -> dict[str, Any]:
        """Every connector's counts and binding, never an endpoint, payload or body."""
        row = await self._one("SELECT app_private.connector_status(%s) AS status", (dead_limit,))
        assert row is not None
        return dict(row["status"])


def _json(value: dict[str, Any]) -> str:
    """Canonical JSON for a parameter, never formatted into a statement."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
