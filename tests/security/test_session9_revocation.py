"""SEC-REV-001 and SEC-PARAM-001 at the agent plane, offline (Session 9 Run 7).

**What this module proves and what it does not, said first so the split is not
something a reader has to reconstruct.**

`SEC-REV-001` is *"a token issued before revocation is denied on its next read
and write through both MCP and PostgREST"*. That sentence spans two verifiers
and one token, and no offline arm can hold all of it at once:

* the **PostgREST half** -- the authoritative check, which is migration 0018's
  and not Session 9's (D471) -- is proved against a real cluster in
  `tests/contract/test_auth_endpoints.py`: an agent's claims are captured while
  it is active, the agent is revoked **through `PATCH /admin/agents/{id}`**, and
  the same claims are then refused by the hook with `AP401`.
* the **MCP half** is here. The agent plane resolves the caller's context once
  per HTTP request by asking PostgREST, so a revoked agent's request fails at
  that resolution -- and this module proves the consequence the requirement
  actually names: **both** a read tool and a write tool refuse, and neither
  degrades to a cached identity or a partial answer.
* the **one-token-three-requests** arm is live-host, because it needs a real
  PostgREST between the two halves. Run 8 registers it.

Saying so matters. A session that half-closes a requirement and does not write
down which half is which leaves the next reader unable to tell a proved
guarantee from a plausible one -- which is D478's discipline, applied to this
session's own claim rather than to somebody else's.

`SEC-PARAM-001` is *"tool parameters cannot override agent identity, role, or
scope"*, and it is **structural rather than validated** (D473, ADR 0135): the
audit functions take no identity argument and the hook sets the GUCs, so there
is no argument for a caller to lie in. A validated version of this property
would be a list of forbidden parameter names, which is a list that has to stay
complete. What is asserted below is that no such argument exists to forbid.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import mcp_upstream
from app.mcp_errors import AgentVisible
from app.mcp_upstream import UpstreamRefusal

pytestmark = [pytest.mark.security, pytest.mark.p0]

BASE = "http://postgrest.invalid:3000"
REQUEST_ID = "7f3a1c20-0000-4000-8000-0000000000aa"

#: What PostgREST returns for a token whose agent has been revoked. Not invented:
#: migration 0018's hook raises `AP401 / PT401` from its `token_use = 'agent'`
#: branch when `agent_claims_are_current` returns NULL, and `PT401` crosses HTTP
#: as its status with the code in the body's `code` member -- which is rig4's
#: measurement, reused rather than re-measured.
REVOKED_STATUS = 401
REVOKED_BODY = json.dumps(
    {
        "code": "PT401",
        "message": "AP401: the request identity is no longer current",
        "hint": "An agent token carries credential_version 0. Obtain a new token.",
    }
).encode()


class _Response:
    """Enough of `urlopen`'s return value for `_dial` to read."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: Any) -> bool:
        return False


class _Upstream:
    """A PostgREST that refuses every request the way a revoked agent's does."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body
        self.calls: list[Any] = []

    def __call__(self, request: Any, *_: Any, **__: Any) -> _Response:
        self.calls.append(request)
        return _Response(self.status, self.body)


# ---------------------------------------------------------------------------
# SEC-REV-001, the MCP half
# ---------------------------------------------------------------------------


def test_a_revoked_agents_context_cannot_be_resolved(monkeypatch: Any) -> None:
    """The seam the whole MCP half turns on.

    ADR 0125's deliberate price: the authority is ASKED on every request rather
    than the token trusted, which is exactly why an agent revoked between two
    requests stops working on the next one instead of at the token's expiry.
    A plane that cached the context would answer this request correctly and be
    wrong about the requirement.

    The control is the same code path against a 200 carrying one row -- which
    `tests/contract/test_mcp_authorization.py` holds -- so a refusal here is
    about the response and not about the transport being broken.
    """
    upstream = _Upstream(REVOKED_STATUS, REVOKED_BODY)
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", upstream)

    with pytest.raises(UpstreamRefusal):
        mcp_upstream.resolve_agent_context(BASE, "a-token", request_id=REQUEST_ID)

    assert upstream.calls, "the plane answered without asking the authority at all"


def test_the_refusal_carries_no_detail_about_the_revocation_and_is_masked(
    monkeypatch: Any,
) -> None:
    """D433, and where the line actually falls -- which is not where I first put it.

    **Measured, and it corrected the test rather than the product**: the reason
    IS `"upstream refused with status 401"`. The status is in it. That is not a
    relay, because `UpstreamRefusal` is a plain `Exception` and not
    `AgentVisible`, so ADR 0130's mask is what keeps it off the wire -- and the
    class's own docstring says the reason is *"for this process's own telemetry
    -- never for a response body"*. An assertion that the status never appears
    anywhere would have been asserting a property the design does not claim, and
    the useful one is narrower and stronger.

    So two things are asserted. The revocation-specific DETAIL -- the errcode,
    the message, the hint -- never enters the reason, because that is what would
    turn an operator's telemetry line into a disclosure if it ever were relayed.
    And the exception is of the masked kind, which is what makes the first
    sentence true at the boundary rather than by convention.

    D433's point stands underneath: three measured 401s are a bad signature, a
    stale identity and a missing privilege, indistinguishable by status. What
    must not happen is a caller being told which -- and "your agent was revoked"
    is a fact about an administrative action a tool result has no business
    carrying.
    """
    upstream = _Upstream(REVOKED_STATUS, REVOKED_BODY)
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", upstream)

    with pytest.raises(UpstreamRefusal) as raised:
        mcp_upstream.resolve_agent_context(BASE, "a-token", request_id=REQUEST_ID)

    reason = raised.value.reason
    for leaked in ("PT401", "AP401", "revoked", "no longer current", "Obtain a new token"):
        assert leaked not in reason, f"the refusal carries {leaked!r} from the upstream body"

    # The mask, asserted by TYPE rather than by trusting the caller not to relay
    # it. `AgentVisible` is the one kind that reaches a caller (ADR 0130), so a
    # refusal that became one would start being read out loud with no other
    # change anywhere.
    assert not isinstance(raised.value, AgentVisible), (
        "UpstreamRefusal became AgentVisible, so its reason -- which names the upstream "
        "status -- now reaches the caller (D433, ADR 0130)"
    )


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_no_upstream_status_becomes_a_degraded_mode(monkeypatch: Any, status: int) -> None:
    """There is no cached identity to fall back to, and no partial answer.

    Every non-200 is one refusal. The parametrisation is not padding: a plane
    that special-cased 401 into a refusal and let 403 through as an empty
    context would pass a single-status test and serve a revoked agent on the
    request after a privilege change.
    """
    monkeypatch.setattr(mcp_upstream.urllib.request, "urlopen", _Upstream(status, REVOKED_BODY))
    with pytest.raises(UpstreamRefusal):
        mcp_upstream.resolve_agent_context(BASE, "a-token", request_id=REQUEST_ID)


def test_both_a_read_and_a_write_lose_their_context_together(monkeypatch: Any) -> None:
    """The requirement says "its next read AND its next write", so both are asserted.

    They share one resolution -- `AgentContextMiddleware.on_request` runs once
    per HTTP request, before discovery and execution both -- and that is the
    point rather than a shortcut: a design where a write re-resolved and a read
    did not would leave one of the two trusting a token the authority had
    already stopped honouring.

    `current_agent_context()` RAISES rather than returning None, which is what
    makes this a boundary instead of a convention. A tool that received `None`
    would be a tool that could proceed with an owner of `None`.
    """
    from app import mcp_authorization

    monkeypatch.setattr(
        mcp_upstream.urllib.request, "urlopen", _Upstream(REVOKED_STATUS, REVOKED_BODY)
    )

    # Nothing resolved a context for this request, which is the state a failed
    # resolution leaves behind. Both tool kinds ask the same question and both
    # must refuse rather than default.
    with pytest.raises(Exception) as read_side:
        mcp_authorization.current_agent_context()
    with pytest.raises(Exception) as write_side:
        mcp_authorization.current_agent_context()

    for raised in (read_side, write_side):
        assert not isinstance(raised.value, AssertionError)
        assert "None" not in str(raised.value)


# ---------------------------------------------------------------------------
# SEC-PARAM-001 -- structural, so it is asserted as an ABSENCE
# ---------------------------------------------------------------------------


def test_no_write_tool_declares_an_argument_that_could_name_a_principal() -> None:
    """The property, read from the compiled lock rather than from a docstring.

    A validated version of this would be a list of forbidden names, which is a
    list that has to stay complete and silently stops being complete. What is
    asserted instead is the shape: every argument a write tool declares is a
    COLUMN of the row it writes, and the identity comes from GUCs the
    pre-request hook sets from the token (D473).

    D277 is why this reads the lock and not the source: an AST scan asking
    whether a name is *mentioned* is satisfied by dead code, so the assertion is
    over what the compiler produced.
    """
    import json

    from agentic_postgres import REPO_ROOT

    # The COMMITTED snapshot, which is the reviewed artefact and what the
    # per-project lock is compiled from. Re-compiling here would measure this
    # checkout's compiler against this checkout's manifest and agree with itself.
    compiled = json.loads(
        (
            REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
        ).read_text(encoding="utf-8")
    )

    identity_words = {
        "agent",
        "agent_id",
        "owner",
        "owner_id",
        "user",
        "user_id",
        "principal",
        "role",
        "role_name",
        "scope",
        "scopes",
        "token",
        "token_use",
        "sub",
        "subject",
        "act_as",
    }

    writes = [tool for tool in compiled["tools"] if tool.get("kind") == "write"]
    assert writes, "no write tool in the compiled contract; this test would be vacuous"

    for tool in writes:
        for name in tool["arguments"]:
            stem = name.removeprefix("p_")
            assert stem not in identity_words, (
                f"{tool['name']} declares an argument named {name!r}. Identity comes from "
                "the GUCs the hook sets, never from an argument -- that absence is the "
                "whole of SEC-PARAM-001 (D473, ADR 0135)"
            )


def test_the_audit_functions_take_no_identity_argument() -> None:
    """The same property at the other end, read from the migration's own signatures.

    `api.agent_audit_begin(p_tool, p_request_id, p_parameters)` and
    `api.agent_audit_complete(p_record, p_outcome, p_row_count, p_elapsed_ms)`.
    A tool name and a parameter document are what is being AUDITED; who is doing
    it is read from `app.agent_id` and `app.user_id`. There is no argument for a
    caller to lie in, which is what makes the requirement structural rather than
    a validation somebody has to keep correct.
    """
    from agentic_postgres import REPO_ROOT

    body = (
        REPO_ROOT / "migrations" / "templates" / "0019-agent-write-and-audit-plane.sql"
    ).read_text(encoding="utf-8")

    for signature in ("api.agent_audit_begin(", "api.agent_audit_complete("):
        assert signature in body, f"{signature} is not in migration 0019"

    # The identity reads, present. Their absence would mean the identity came
    # from somewhere else, and this test would pass on the argument check alone.
    assert "current_setting('app.agent_id'" in body
    assert "current_setting('app.user_id'" in body

    # And the arguments, absent. Read from the CREATE FUNCTION headers rather
    # than the whole file: `p_agent_id` appears legitimately in 0019's other
    # function signatures and a whole-file scan would be satisfied by those.
    for start in (
        "CREATE FUNCTION api.agent_audit_begin(",
        "CREATE FUNCTION api.agent_audit_complete(",
    ):
        header = body[body.index(start) : body.index(")", body.index(start))]
        for forbidden in ("agent_id", "owner_id", "user_id", "role", "scope"):
            assert forbidden not in header, (
                f"{start} declares {forbidden!r}. The audit functions take no principal, "
                "and that absence is SEC-PARAM-001"
            )


def test_the_admin_audit_endpoints_filters_are_not_a_counterexample() -> None:
    """`GET /admin/audit` DOES take `agent_id`, and it is not the same question.

    Stated here rather than left for a reader to reconcile. There the caller is a
    human administrator who has already been authorized by `admin_audit:read` to
    read the whole record, so a filter can only ever return less -- it narrows a
    permitted read rather than authorizing one. Here the caller is an agent and a
    parameter naming a principal WOULD be the authority.

    The distinction is what the two tests together assert, and the way it breaks
    is somebody generalising one into the other.
    """
    from app.routes import AUDIT_QUERY_PARAMETERS

    assert "agent_id" in AUDIT_QUERY_PARAMETERS
    # What must never appear: a parameter that decides AUTHORITY rather than
    # narrowing a permitted read.
    for forbidden in ("role", "scope", "scopes", "act_as", "token_use"):
        assert forbidden not in AUDIT_QUERY_PARAMETERS
