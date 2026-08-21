"""What an agent is told, and what it deliberately is not (ADR 0130).

`errors.py`'s shape, applied to the agent plane, and with one thing that surface
does not have: **the framework decides whether a message escapes at all.**

Measured on the pinned version, against a masked server and an unmasked control:

    a plain Exception("column 'secret' is not queryable")
        masked   -> "Error calling tool 'query_resource'"     the message is gone
        control  -> "... : column 'secret' is not queryable"

    ToolError("column 'secret' is not queryable")
        masked   -> "column 'secret' is not queryable"        it passes through
        control  -> the same

So `ToolError` is the framework's designated caller-facing channel and it
bypasses `mask_error_details`. That is ADR 0097's split already expressed in the
framework's own vocabulary: **silence by default, and one explicit type for what
a caller may be told.**

**The mask stays on**, and that is what makes this a boundary rather than a
convention. A new plain exception is silent by default, so telling a caller
something is the act that requires a decision -- not hiding it.

**Run 6's refusals reached nobody.** `ToolRefusal` was a plain exception, so
every message it raised -- `"secret is not a filterable column of notes"`,
`"this resource requires ['notes:read', 'tasks:read']"` -- was replaced by the
framework's opaque string before it left the process. They were written,
reviewed and tested, and were invisible. D274's shape.
"""

from __future__ import annotations

from typing import Final

#: What a caller may be told, as stable machine tokens.
#:
#: A token and a sentence, in `errors.py`'s spirit: the token is what a client
#: branches on, and the sentence is for a human reading a transcript. Neither
#: names a schema, an upstream status, or a row the caller did not receive.
INPUT_NOT_PERMITTED: Final = "input_not_permitted"
SCOPE_NOT_HELD: Final = "scope_not_held"
BUDGET_EXCEEDED: Final = "budget_exceeded"
RESOURCE_UNKNOWN: Final = "resource_unknown"

#: Every token a caller can see. Enumerated so a test can assert the set, and so
#: adding one is an edit somebody reviews rather than a string somebody types.
CALLER_FACING_TOKENS: Final = (
    BUDGET_EXCEEDED,
    INPUT_NOT_PERMITTED,
    RESOURCE_UNKNOWN,
    SCOPE_NOT_HELD,
)

#: The one thing every structural refusal says, and it says nothing.
#:
#: Not raised as `ToolError`: this constant is the *log's* reason, and the caller
#: gets the framework's opaque string because a plain exception is masked. D433
#: is why there is no variant per cause -- the three upstream 401s measured are a
#: bad signature, a stale identity and a missing privilege, indistinguishable by
#: status, so relaying one would be a guess dressed as a diagnosis.
STRUCTURAL_REFUSAL: Final = "refused"


class AgentVisible(Exception):
    """A refusal an authenticated agent may read, and act on.

    Raised through `as_tool_error` at the boundary rather than being a
    `ToolError` subclass, so that the modules which detect a refusal -- the query
    builder, the lock reader -- need no framework import and stay testable
    without one.
    """

    def __init__(self, token: str, detail: str) -> None:
        if token not in CALLER_FACING_TOKENS:
            raise ValueError(f"{token!r} is not a caller-facing token")
        super().__init__(detail)
        self.token = token
        self.detail = detail

    def __str__(self) -> str:
        return f"{self.token}: {self.detail}"


def as_tool_error(error: AgentVisible) -> Exception:
    """Wrap a caller-visible refusal in the type the framework lets through.

    The import is local for the reason every framework import in this package is:
    the refusal branches stay reachable in a test that has not built a server.
    """
    from fastmcp.exceptions import ToolError

    return ToolError(str(error))
