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
WRITE_CONFLICT: Final = "write_conflict"
ROW_NOT_FOUND: Final = "row_not_found"

#: Every token a caller can see. Enumerated so a test can assert the set, and so
#: adding one is an edit somebody reviews rather than a string somebody types.
#: `write_conflict` and `row_not_found` are Session 9's (ADR 0139): a
#: compare-and-swap a caller cannot distinguish from a generic failure is not
#: one.
CALLER_FACING_TOKENS: Final = (
    BUDGET_EXCEEDED,
    INPUT_NOT_PERMITTED,
    RESOURCE_UNKNOWN,
    ROW_NOT_FOUND,
    SCOPE_NOT_HELD,
    WRITE_CONFLICT,
)

#: The product's own write-refusal vocabulary, translated (ADR 0139).
#:
#: The keys are the `PT` errcodes migration 0019's write RPCs raise; a test
#: compares them against the migration template so a key the product never
#: raises cannot sit here looking meaningful. The sentences are THIS
#: repository's, reviewed here -- the upstream message, details and hint are
#: discarded, because they are the product's today and an arbitrary string
#: after the next migration (ADR 0097).
#:
#: **Measured, not assumed** (rig4): PostgREST maps `ERRCODE PTxxx` to HTTP
#: status xxx with the errcode in the body's `code` member -- and status alone
#: cannot classify a refusal, because a missing argument (`PGRST202`) and the
#: product's "no such task" (`PT404`) are BOTH a 404. Only the body's code
#: tells "the function you built a request for does not exist" from "the row
#: you named does not exist".
#:
#: `PT401` is deliberately absent: a caller that reached a tool has already
#: been authenticated, so a missing request identity there is a fault, not an
#: instruction. Everything unmapped stays masked (ADR 0130).
UPSTREAM_WRITE_REFUSALS: Final[dict[str, tuple[str, str]]] = {
    "PT404": (ROW_NOT_FOUND, "the row this write names does not exist"),
    "PT409": (WRITE_CONFLICT, "the row is not in the expected state; re-read and retry"),
    "PT422": (INPUT_NOT_PERMITTED, "this transition would change nothing"),
}


def write_refusal(code: str) -> AgentVisible | None:
    """The caller-visible form of one upstream write refusal, or None.

    None means "not the caller's to read": the refusal stays structural and the
    framework's mask replaces it. The mapping is total over the enumerated
    vocabulary and refuses to guess about anything outside it.
    """
    translated = UPSTREAM_WRITE_REFUSALS.get(code)
    if translated is None:
        return None
    token, sentence = translated
    # `write_rejected`: the product's OWN PT4xx vocabulary, translated
    # (ADR 0139). Distinct from `upstream_refused`, which is a status this
    # plane could not classify -- these three it can, because the product
    # raised them deliberately and this repository reviewed the sentences.
    return AgentVisible(token, sentence, WRITE_REJECTED)


#: The one thing every structural refusal says, and it says nothing.
#:
#: Not raised as `ToolError`: this constant is the *log's* reason, and the caller
#: gets the framework's opaque string because a plain exception is masked. D433
#: is why there is no variant per cause -- the three upstream 401s measured are a
#: bad signature, a stale identity and a missing privilege, indistinguishable by
#: status, so relaying one would be a guess dressed as a diagnosis.
STRUCTURAL_REFUSAL: Final = "refused"


# ---------------------------------------------------------------------------
# What the AUDIT RECORD says, which is a third thing (ADR 0178)
# ---------------------------------------------------------------------------
#
# Not `CALLER_FACING_TOKENS` and not `STRUCTURAL_REFUSAL`. Those answer *what may
# an agent be told*, and the answer is deliberately little: six tokens, and one
# string for everything else.
#
# A denial reason answers a different question -- *which boundary refused* -- and
# it is read by an operator, in a console, later. It has to separate the cases a
# caller is told nothing about, or a deployment fault, an unreachable upstream
# and an unwritable audit table all arrive as `refused`.
#
# **Derived from the refusal sites, not designed beside them.** The session plan
# proposed five members and named `credential`; there is no such refusal here.
# This runtime holds no credential of any kind, and classifying an upstream 401
# as one is D433's forbidden guess -- `mcp_upstream`'s own header measures four
# states behind two statuses. `UPSTREAM_REFUSED` is the honest form: this plane
# asked and was told no.
SCOPE_NOT_HELD_REASON: Final = "scope_not_held"
NOT_IN_ALLOWLIST: Final = "not_in_allowlist"
INPUT_MALFORMED: Final = "input_malformed"
BUDGET_EXCEEDED_REASON: Final = "budget_exceeded"
CONTRACT_DRIFT: Final = "contract_drift"
UPSTREAM_REFUSED: Final = "upstream_refused"
AUDIT_UNAVAILABLE: Final = "audit_unavailable"
WRITE_REJECTED: Final = "write_rejected"

#: Every member, in the enum's own order. A contract test compares this tuple
#: against migration 0027's template, so the catalog and this file cannot drift
#: apart and neither is a second authority (ADR 0002). The comparison is the
#: same one `UPSTREAM_WRITE_REFUSALS`'s keys already get against 0019.
DENIAL_REASONS: Final = (
    SCOPE_NOT_HELD_REASON,
    NOT_IN_ALLOWLIST,
    INPUT_MALFORMED,
    BUDGET_EXCEEDED_REASON,
    CONTRACT_DRIFT,
    UPSTREAM_REFUSED,
    AUDIT_UNAVAILABLE,
    WRITE_REJECTED,
)

#: The caller-facing token each denial reason accompanies, where there is one.
#:
#: `None` means the caller is told nothing -- the three structural classes plus
#: the audit one. The mapping is here rather than at each raise site so that
#: "which reason goes with which token" is one table somebody can read, and so
#: the guard below can assert it is total over `DENIAL_REASONS`.
TOKEN_FOR_REASON: Final[dict[str, str | None]] = {
    SCOPE_NOT_HELD_REASON: SCOPE_NOT_HELD,
    NOT_IN_ALLOWLIST: INPUT_NOT_PERMITTED,
    INPUT_MALFORMED: INPUT_NOT_PERMITTED,
    BUDGET_EXCEEDED_REASON: BUDGET_EXCEEDED,
    CONTRACT_DRIFT: None,
    UPSTREAM_REFUSED: None,
    AUDIT_UNAVAILABLE: None,
    WRITE_REJECTED: WRITE_CONFLICT,
}


def denial_reason(reason: str) -> str:
    """Validate a denial reason at the point it is chosen, not at the database.

    The column's type would refuse an unknown value anyway, and that refusal
    arrives as a constraint violation inside an audit call -- which the write
    path treats as `audit_unavailable` and fails closed on. So a typo here would
    surface as "the audit table is broken", which is the wrong diagnosis for a
    misspelled constant and the expensive kind of wrong.
    """
    if reason not in DENIAL_REASONS:
        raise ValueError(f"{reason!r} is not a denial reason")
    return reason


class AgentVisible(Exception):
    """A refusal an authenticated agent may read, and act on.

    Raised through `as_tool_error` at the boundary rather than being a
    `ToolError` subclass, so that the modules which detect a refusal -- the query
    builder, the lock reader -- need no framework import and stay testable
    without one.
    """

    def __init__(self, token: str, detail: str, reason: str) -> None:
        """`reason` is REQUIRED, and that is the decision (ADR 0178).

        A default would be one member standing for several boundaries, which is
        exactly the collapse `STRUCTURAL_REFUSAL` makes deliberately for a
        CALLER and which an operator's console must not inherit. The caller-side
        token and the audit-side reason are validated separately because they
        are different vocabularies answering different questions.
        """
        if token not in CALLER_FACING_TOKENS:
            raise ValueError(f"{token!r} is not a caller-facing token")
        super().__init__(detail)
        self.token = token
        self.detail = detail
        self.reason = denial_reason(reason)

    def __str__(self) -> str:
        return f"{self.token}: {self.detail}"


def as_tool_error(error: AgentVisible) -> Exception:
    """Wrap a caller-visible refusal in the type the framework lets through.

    The import is local for the reason every framework import in this package is:
    the refusal branches stay reachable in a test that has not built a server.
    """
    from fastmcp.exceptions import ToolError

    return ToolError(str(error))
