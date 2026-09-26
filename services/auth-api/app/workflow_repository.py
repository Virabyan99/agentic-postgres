"""The workflow calls: eight of migration 0034's substrate and seven of 0035's.

Since Session 33 the gates -- requesting, reading, expiring and deciding an
approval -- the approvals listing, the signer's lookup and provenance are here
too (ADR 0230-0234), each one definer function like the eight before them.

`auth_service` holds **no privilege of any kind on the four workflow tables** --
not SELECT, not INSERT, not UPDATE, not DELETE (0034, and
`test_workflow_substrate.py::test_no_role_holds_a_privilege_on_the_four_tables`
asserts it for seven roles across four tables and four privileges). Everything
below goes through a `SECURITY DEFINER` function, which is what makes the
ownership and lease rules unbypassable by this code rather than merely
unbypassed by it: there is no statement this role could issue that moves a step
it does not hold, however the service is later edited.

**The ninth function is deliberately absent.** `workflow_install_definition` is
granted to NOBODY (ADR 0228): the deploy calls it as the bootstrap superuser
through the container, and a method here would be a definition-writing authority
behind an identity reachable over HTTP. A reader looking for it finds this
paragraph instead of a gap.

**Each method is one autocommit round trip and holds nothing open.** ADR 0104's
reasoning applies to the claim in particular: the TOOL CALL happens between
`claim` and `finish`, not inside either, because a transaction held across a
network call is a lock whose duration is set by that network call. The lease --
not a row lock -- is what survives the gap, which is the whole of ADR 0227.

**Nothing here is formatted into a statement.** Every value is a parameter, and
the statements are literals in this module. That is not defence in depth against
this module's own callers; it is what lets
`test_the_workflow_repository_formats_no_statement` be a scan rather than a
judgement.

**This module exists in RUN 3 rather than Run 5, and the reason is a guard
working** (D1680). `test_every_granted_function_has_a_caller` refuses a `GRANT
EXECUTE` on a function no code calls -- *"a grant nobody can audit against a
caller that does not exist"*, 0011's rule, guarded as a class since D837. Its
docstring names the failure shape exactly: *"the shape of a plane half-built one
run early."* Shipping 0034's grants without their caller is that shape, so the
caller ships with the grants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass(frozen=True, slots=True)
class ClaimedStep:
    """One leased step: what to call, with what, and under which key.

    `attempt` is incremented on CLAIM rather than on success (0034), so a step
    that keeps killing its worker is visible as a rising attempt rather than as
    a row that never moves -- `storage_objects.cleanup_attempts`' reasoning, one
    plane over.

    `prior` carries the succeeded steps' results by name, so a step's arguments
    can reference an earlier one without this process holding run state between
    claims. The loop is stateless by construction: everything it needs to
    execute a step arrives in the claim.
    """

    step_id: UUID
    run_id: UUID
    position: int
    name: str
    attempt: int
    # No `request_id` (D1696). The id that correlates a step to the plane's
    # audit is the one the PLANE mints for the call and returns on its
    # response; it does not exist when a step is claimed, and the plane
    # ignores any id a caller sends (ADR 0160). `finish` and `park` take it.
    agent_id: UUID
    dry_run: bool
    step: dict[str, Any]
    input: dict[str, Any]
    prior: dict[str, Any]
    timeout_seconds: int
    idempotency_key: str


class WorkflowRepository:
    """The substrate, as the auth service's own role sees it."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def _one(self, statement: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
        async with self._pool.connection() as connection:
            cursor = connection.cursor(row_factory=dict_row)
            await cursor.execute(statement, parameters)
            return await cursor.fetchone()

    async def heartbeat(self, *, holder: str) -> None:
        """Record that this loop asked for work.

        Written at every poll, not at every claim: a loop that finds nothing to
        do is still alive, and a heartbeat that only moved on work would report
        an idle deployment as a dead one.
        """
        await self._one("SELECT app_private.workflow_heartbeat(%s)", (holder,))

    async def claim(self, *, holder: str, lease_margin_seconds: int) -> ClaimedStep | None:
        """Lease at most one step. `None` means there is nothing to do.

        The lease outlives this round trip and that is the point (ADR 0104, ADR
        0227): the tool call happens afterwards, and a row lock would be
        released at COMMIT and at crash. A worker that dies mid-call loses its
        hold by EXPIRY, which is the only mechanism that survives the process.

        **A MARGIN, not a lease** (D1687). The lease the function takes is the
        step's own `timeout_seconds` plus this, computed inside the function,
        because the step's timeout arrives in this call's own RESULT -- a
        caller passing an absolute lease could only pass the ceiling, and a
        worker that died mid-call would leave its step unclaimable for ten
        minutes. The margin is a function of the worker's HTTP client
        (`workflow_worker.lease_margin_seconds`), never a constant here.
        """
        row = await self._one(
            "SELECT step_id, run_id, step_position, step_name, attempt, "
            "agent_id, dry_run, step, input, prior, timeout_seconds, idempotency_key "
            "FROM app_private.workflow_claim_step(%s, %s)",
            (holder, lease_margin_seconds),
        )
        if row is None:
            return None
        return ClaimedStep(
            step_id=row["step_id"],
            run_id=row["run_id"],
            # `step_position` and `step_name` are the function's spelling, not
            # this dataclass's: `position` is a col_name_keyword and is a syntax
            # error as a bare OUT parameter in RETURNS TABLE (D1675).
            position=int(row["step_position"]),
            name=row["step_name"],
            attempt=int(row["attempt"]),
            agent_id=row["agent_id"],
            dry_run=bool(row["dry_run"]),
            step=row["step"] or {},
            input=row["input"] or {},
            prior=row["prior"] or {},
            timeout_seconds=int(row["timeout_seconds"]),
            idempotency_key=row["idempotency_key"],
        )

    async def finish(
        self,
        *,
        step_id: UUID,
        holder: str,
        outcome: str,
        result: str | None,
        reason: str | None,
        request_id: UUID | None,
    ) -> str:
        """Close one step and learn the RUN's new status in the same round trip.

        Returns `'lease_lost'` when this holder no longer holds the step, and
        **the caller must not treat that as an error**: the lease expired while
        the call was in flight, a successor holds the row, and the work was
        still done. `storage_finish_cleanup`'s rule, one plane over.

        `result` is a JSON string rather than a dict because the parameter is
        cast to `jsonb` by the statement; serialising at the boundary keeps one
        serializer rather than two.

        `request_id` is the id the PLANE returned on its response, or `None`
        when this attempt made no call (D1696) -- the value that joins this
        step to `app_private.agent_audit`.
        """
        row = await self._one(
            "SELECT app_private.workflow_finish_step(%s, %s, %s, %s::jsonb, %s, %s) AS status",
            (step_id, holder, outcome, result, reason, request_id),
        )
        assert row is not None
        return str(row["status"])

    async def park(
        self,
        *,
        step_id: UUID,
        holder: str,
        reason: str,
        resume_after: Any,
        request_id: UUID | None,
    ) -> str:
        """Defer one step until a time, releasing its lease.

        **Park IS the backoff** (ADR 0227). There is no sleep in the loop and no
        second waiting mechanism: a retryable failure sets a time, and the
        claim's own predicate is what brings the step back. Returns
        `'lease_lost'` on the same terms `finish` does. A park follows a call
        the plane answered, so it records the plane's id as `finish` does.
        """
        row = await self._one(
            "SELECT app_private.workflow_park(%s, %s, %s, %s, %s) AS outcome",
            (step_id, holder, reason, resume_after, request_id),
        )
        assert row is not None
        return str(row["outcome"])

    async def enqueue(
        self,
        *,
        agent_id: UUID,
        name: str,
        version: int,
        run_input: str,
        dry_run: bool,
    ) -> UUID:
        """Start one run as one agent. The route's call, not the loop's.

        The AGENT's stored scopes authorise it, checked inside the function
        against the definition's `required_scopes` -- so an agent narrowed
        between minting a token and starting a run is refused by the database
        rather than by anything this process remembers (ADR 0229).
        """
        row = await self._one(
            "SELECT app_private.workflow_enqueue(%s, %s, %s, %s::jsonb, %s) AS run_id",
            (agent_id, name, version, run_input, dry_run),
        )
        assert row is not None
        return row["run_id"]

    async def cancel(self, *, run_id: UUID, agent_id: UUID) -> str:
        """Cancel the AGENT'S OWN run and return its status.

        A queued run is cancelled at once; a running one records an intent the
        next claim honours, because a tool call already upstream cannot be
        recalled. Another agent's run raises the same refusal a missing one
        does, so neither leaks the other's existence.
        """
        row = await self._one(
            "SELECT app_private.workflow_cancel(%s, %s) AS status",
            (run_id, agent_id),
        )
        assert row is not None
        return str(row["status"])

    async def status(self, *, run_id: UUID, agent_id: UUID) -> dict[str, Any]:
        """The AGENT'S OWN run, whole, as one document."""
        row = await self._one(
            "SELECT app_private.workflow_run_status(%s, %s) AS document",
            (run_id, agent_id),
        )
        assert row is not None
        return dict(row["document"])

    async def counts(self) -> dict[str, Any]:
        """Runs and steps by status, the ages, and the holder. No verdict.

        The doctor's twelfth check reports these and decides nothing (D1441):
        nobody has measured a run count at which a deployment is unwell.
        """
        row = await self._one("SELECT app_private.workflow_counts() AS counts", ())
        assert row is not None
        return dict(row["counts"])

    # -- the gates, and provenance (migration 0035, ADR 0230-0234) ----------
    #
    # Seven more calls, each one definer function, shipped in the same commit
    # as the grants that name them (D1680). `workflow_begin_compensation` is
    # the one 0035 function with NO method here, and that is its grant's
    # absence stated a second time: only 0035's own functions call it.

    async def request_approval(
        self, *, step_id: UUID, holder: str, request_id: UUID | None, expires_after_seconds: int
    ) -> str:
        """Park an approval step on the PLANE's `approval_required` refusal.

        `request_id` is the plane's id of the refused call (D1696), which is
        what joins the approval to its audit row. Returns `'parked'`, or
        `'lease_lost'` on the terms `finish` does (ADR 0230).
        """
        row = await self._one(
            "SELECT app_private.workflow_request_approval(%s, %s, %s, %s) AS outcome",
            (step_id, holder, request_id, expires_after_seconds),
        )
        assert row is not None
        return str(row["outcome"])

    async def gate_state(self, *, step_id: UUID, holder: str) -> dict[str, Any]:
        """The loop's ONE read at a gate: the approval, and whether a wait was served."""
        row = await self._one(
            "SELECT app_private.workflow_gate_state(%s, %s) AS state", (step_id, holder)
        )
        assert row is not None
        return dict(row["state"])

    async def expire_approval(self, *, step_id: UUID, holder: str) -> str:
        """Mark a pending approval past its expiry `expired`; a decided one never moves."""
        row = await self._one(
            "SELECT app_private.workflow_expire_approval(%s, %s) AS outcome", (step_id, holder)
        )
        assert row is not None
        return str(row["outcome"])

    async def decide(self, *, run_id: UUID, step: str, user_id: UUID, decision: str) -> str:
        """A human's decision, final (ADR 0230, ADR 0232).

        The route's call, not the loop's. The function refuses the run's owner,
        a decided approval and an expired one before it writes anything, and
        the route reads its message for one word.
        """
        row = await self._one(
            "SELECT app_private.workflow_decide_approval(%s, %s, %s, %s) AS approval",
            (run_id, step, user_id, decision),
        )
        assert row is not None
        return str(row["approval"])

    async def pending_approvals(self, *, limit: int) -> list[dict[str, Any]]:
        """What waits for a human, oldest first, with no argument value (D1720)."""
        row = await self._one(
            "SELECT app_private.workflow_pending_approvals(%s) AS approvals", (limit,)
        )
        assert row is not None
        return list(row["approvals"])

    async def approval_for_token(
        self, *, approval_id: UUID, agent_id: UUID
    ) -> dict[str, str] | None:
        """The tool and key of an APPROVED approval of this agent's running run.

        `None` means refuse (ADR 0231). The signer reads this before it adds
        `apg_approval` to one step token, so the claim's content comes from a
        decided row and never from the loop's own variables.
        """
        row = await self._one(
            "SELECT tool, idempotency_key FROM app_private.workflow_approval_for_token(%s, %s)",
            (approval_id, agent_id),
        )
        if row is None:
            return None
        return {"tool": row["tool"], "key": row["idempotency_key"]}

    async def provenance(self, *, run_id: UUID) -> dict[str, Any]:
        """One run, for an auditor (ADR 0234). Never parameters, never a result."""
        row = await self._one("SELECT app_private.workflow_provenance(%s) AS document", (run_id,))
        assert row is not None
        return dict(row["document"])
