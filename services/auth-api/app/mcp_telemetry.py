"""One structured record per tool call. Durable nowhere (ADR 0130, D412).

**Telemetry, not audit, and the distinction is the decision.** Telemetry answers
"what happened" for an operator watching a running deployment. An audit record
answers "what happened" for a record-keeper, months later, with a fail-closed
contract about what happens when it cannot be written. They are not the same
artefact, and `mcp_audit_service` -- a role that has existed unactivated since
Session 3 -- stays unactivated because Session 9 owns that contract.

**What a record carries** is the tool, the resource, the outcome, the row count,
the elapsed milliseconds, and the agent and owner ids.

**What it may never carry**, and this is the canary's list:

    a token, or any fingerprint of one
    a URL
    an object key
    ANY caller value -- a filter operand, a column projection, or a row

The ids are deliberate and the values are deliberately absent. An owner id names
a principal the deployment already knows about; a note title is content. The
distinction is not fussiness: this log is read by operators and shipped by the
journal, and Session 7's canary scan exists because a presigned URL reached one.

**A logged traceback carries no caller data, and that was measured rather than
assumed** (D449). The first guess -- written here before it was checked -- was
that a `rich` panel through the query builder renders frame locals, where a
caller's filter operand lives. It does not: `show_locals` is never set anywhere
in the framework's logging setup, so `RichHandler`'s default of `False` applies
and a panel shows this repository's own source lines and nothing of the request.
**It is a default, not a pin**, so a framework bump has to re-check it.

What this module enforces is narrower and is its own: an unclassified failure is
logged with the exception's **type** and never its message, because a message is
where a caller's value would be if one ever reached one.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("apg.mcp")

#: Every field a record may contain. Enumerated rather than left to whatever a
#: call site passes, so that adding one is an edit a reviewer sees -- and so the
#: canary test can assert the set rather than grep for what it fears.
RECORD_FIELDS = (
    "agent_id",
    "elapsed_ms",
    "outcome",
    "owner_id",
    "resource",
    "row_count",
    "tool",
)

#: Outcomes, closed. `refused` covers both refusal channels: a caller-visible
#: input refusal and a masked structural one are the same event to an operator
#: counting them, and the reason is a separate field only where it is safe.
OUTCOME_SERVED = "served"
OUTCOME_REFUSED = "refused"
OUTCOME_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReadRecord:
    """One tool call, as the log sees it."""

    tool: str
    resource: str | None
    outcome: str
    agent_id: str | None
    owner_id: str | None
    row_count: int | None
    elapsed_ms: int

    def as_dict(self) -> dict[str, Any]:
        record = {
            "tool": self.tool,
            "resource": self.resource,
            "outcome": self.outcome,
            "agent_id": self.agent_id,
            "owner_id": self.owner_id,
            "row_count": self.row_count,
            "elapsed_ms": self.elapsed_ms,
        }
        if set(record) != set(RECORD_FIELDS):
            # A field added to the dataclass and not to the list, or the other
            # way round. Raised rather than logged: a record whose shape nobody
            # declared is a record the canary test is not checking.
            raise ValueError(f"the record shape and {RECORD_FIELDS} disagree")
        return record


class Timed:
    """Measures one tool call and emits exactly one record for it.

    A context manager rather than a decorator, because the outcome is decided
    inside the body and the row count is not known until the end -- and because
    a decorator would have to guess which exceptions mean `refused`.
    """

    def __init__(self, tool: str, *, resource: str | None = None) -> None:
        self.tool = tool
        self.resource = resource
        self.outcome = OUTCOME_FAILED
        self.row_count: int | None = None
        self.agent_id: str | None = None
        self.owner_id: str | None = None
        self._started = 0.0

    def __enter__(self) -> Timed:
        self._started = time.monotonic()
        return self

    def served(self, row_count: int | None = None) -> None:
        self.outcome = OUTCOME_SERVED
        self.row_count = row_count

    def refused(self) -> None:
        self.outcome = OUTCOME_REFUSED

    def principal(self, *, agent_id: str | None, owner_id: str | None) -> None:
        self.agent_id = agent_id
        self.owner_id = owner_id

    def __exit__(self, kind: Any, value: Any, traceback: Any) -> None:
        del value, traceback
        if kind is not None and self.outcome == OUTCOME_FAILED:
            # An exception the body did not classify. Left as `failed`, and the
            # TYPE is named -- never the message, which is where a caller's
            # value would be if one ever reached an exception string.
            LOGGER.warning(
                "apg.mcp.read %s", json.dumps({**self._record(), "error": kind.__name__})
            )
            return
        LOGGER.info("apg.mcp.read %s", json.dumps(self._record()))

    def _record(self) -> dict[str, Any]:
        return ReadRecord(
            tool=self.tool,
            resource=self.resource,
            outcome=self.outcome,
            agent_id=self.agent_id,
            owner_id=self.owner_id,
            row_count=self.row_count,
            elapsed_ms=int((time.monotonic() - self._started) * 1000),
        ).as_dict()
