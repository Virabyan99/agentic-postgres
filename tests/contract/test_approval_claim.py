"""The signed approval claim: minted only from a decision, honoured only for its call.

`AGT-APPROVE-002` (ADR 0231). **Two halves, each driven through the real code.**

*The signer's half* drives a REAL `AuthService` with a generated key and a
repository fake that answers `approval_for_token` the way
`workflow_approval_for_token` does -- a row for an approved decision on a
running run of that agent, nothing otherwise. The claim's tool and key must
come from that answer and from nowhere else.

*The plane's half* drives `mcp_tools.invoke_write` -- and, for the wiring, the
registered write closure -- against a lock whose write requires approval, with
`execute_write` replaced by a recorder. The load-bearing assertion in every
refusal is that NOTHING WAS DIALLED; the control is that a token without the
claim is refused with the same bytes it has always been refused with.

Nothing here reaches a database, a network or a container.
"""

from __future__ import annotations

import ast
import asyncio
import json
import tempfile
from typing import Any, ClassVar
from uuid import UUID, uuid4

import jwt
import pytest
from tests.contract.test_mcp_tools import (
    BASE,
    IDEMPOTENCY_KEY,
    REQUEST_ID,
    _registered,
    _Registry,
    _relocked,
)
from tests.contract.test_workflow_routes import NoHasher, _lock_document, _signing_key

from agentic_postgres import REPO_ROOT, service_source
from app import claims, mcp_authorization, mcp_errors, mcp_tools
from app.mcp_errors import AgentVisible

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

service_module = service_source.load("service")
repository_module = service_source.load("repository")
errors = service_source.load("errors")

AGENT = uuid4()
APPROVAL = uuid4()
STEP_KEY = "wf-00000000-0000-4000-8000-000000000001-set_the_embedding"

#: The refusal every caller without a matching claim has always received. The
#: bytes are the control: Session 33 changed WHO can pass, not what the others
#: are told.
REFUSAL_TEXT = (
    "approval_required: this capability requires an approval this deployment cannot grant"
)


# ---------------------------------------------------------------------------
# The signer
# ---------------------------------------------------------------------------


class DecisionRepository:
    """`lookup_agent` for one agent, and `approval_for_token` for one decision."""

    def __init__(self, credential: Any, decided: dict[tuple[UUID, UUID], dict[str, str]]) -> None:
        self._credential = credential
        self._decided = decided
        self.asked: list[tuple[UUID, UUID]] = []

    async def lookup_agent(self, agent_id: UUID) -> Any:
        return self._credential if agent_id == self._credential.agent_id else None

    async def approval_for_token(self, *, approval_id: UUID, agent_id: UUID) -> Any:
        self.asked.append((approval_id, agent_id))
        return self._decided.get((approval_id, agent_id))


@pytest.fixture(scope="module")
def signer() -> Any:
    tokens = service_source.load("tokens")
    scope_map = service_source.load("scopes")
    private = _signing_key()
    credential = repository_module.AgentCredential(
        agent_id=AGENT,
        role_name="apg_fixture_alpha_dev_agent_writer",
        scopes=["note_embeddings:write", "tasks:write"],
        status="active",
        authz_version=3,
        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$aGFzaA",  # noqa: S106
        secret_expired=False,
    )
    lock = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
    lock.write(json.dumps(_lock_document()))
    lock.close()
    repository = DecisionRepository(
        credential,
        {(APPROVAL, AGENT): {"tool": "set_note_embedding", "key": STEP_KEY}},
    )
    return service_module.AuthService(
        repository=repository,
        hasher=NoHasher(),
        signing_key=private,
        key_set=tokens.LocalKeySet.load(json.dumps(private.jwks()).encode("utf-8")),
        issuer="https://approval-claim.invalid",
        audience="approval-claim",
        role_suffixes={"apg_fixture_alpha_dev_agent_writer": "agent_writer"},
        vocabulary=scope_map.load_vocabulary(lock.name),
    )


def _payload(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


def test_step_token_adds_the_claim_only_from_an_approved_decision(signer: Any) -> None:
    """The claim's `tool` and `key` are the REPOSITORY's answer for (approval,
    agent) -- and a step token minted without an approval carries no claim."""
    signer.repository.asked.clear()
    issued = asyncio.run(signer.step_token(str(AGENT), approval_id=str(APPROVAL)))
    payload = _payload(issued.token)
    assert payload[claims.APPROVAL_CLAIM] == {
        "id": str(APPROVAL),
        "tool": "set_note_embedding",
        "key": STEP_KEY,
    }
    assert signer.repository.asked == [(APPROVAL, AGENT)], (
        "the signer did not ask the database about THIS approval for THIS agent"
    )
    # The token is still one the verifier accepts, and the claim reads back.
    verified = claims.verify_claims(
        payload, issuer=signer.issuer, audience=signer.audience, now=payload["iat"]
    )
    assert claims.approval_claim(verified) == payload[claims.APPROVAL_CLAIM]

    plain = _payload(asyncio.run(signer.step_token(str(AGENT))).token)
    assert claims.APPROVAL_CLAIM not in plain
    # Everything else is the same authority (rig 32f's comparison, kept).
    for name in ("sub", "role", "scope", "token_use", "authz_version", "credential_version"):
        assert plain[name] == payload[name], name


def test_step_token_refuses_an_undecided_or_foreign_approval(signer: Any) -> None:
    """No row, no token -- never a token without the claim, which the loop
    would then spend on a call the plane refuses. An approval of ANOTHER
    agent's run is no row, because the lookup is keyed by the agent."""
    for approval_id in (str(uuid4()), "not-a-uuid"):
        with pytest.raises(errors.AuthenticationFailed, match="not decided for this agent"):
            asyncio.run(signer.step_token(str(AGENT), approval_id=approval_id))

    other = uuid4()
    signer.repository.asked.clear()
    with pytest.raises(errors.AuthenticationFailed):
        asyncio.run(signer.step_token(str(other), approval_id=str(APPROVAL)))
    assert signer.repository.asked == [], (
        "an unknown agent reached the approval lookup; the agent's own checks come first"
    )


def test_agent_token_never_carries_the_claim() -> None:
    """`/auth/agent-token` takes an agent's secret and nothing else, so the
    one function behind it may not name the extra-claims door at all."""
    tree = ast.parse(
        (REPO_ROOT / "services" / "auth-api" / "app" / "service.py").read_text("utf-8")
    )
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "agent_token"
    )
    named = {
        node.arg for node in ast.walk(function) if isinstance(node, ast.keyword) and node.arg
    } | {node.id for node in ast.walk(function) if isinstance(node, ast.Name)}
    assert "extra_claims" not in named
    assert "APPROVAL_CLAIM" not in ast.unparse(function)

    # And the one caller that does pass it is `step_token`.
    callers = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name != "issue"
        and any(
            isinstance(inner, ast.keyword) and inner.arg == "extra_claims"
            for inner in ast.walk(node)
        )
    ]
    assert callers == ["step_token"], callers


def test_issue_refuses_an_extra_claim_naming_a_required_one(signer: Any) -> None:
    credential = signer._as_credential(signer.repository._credential)
    for name in ("scope", "sub", "role", "exp"):
        with pytest.raises(errors.InvalidRequest, match="may not name a required one"):
            signer.issue(credential, token_use="agent", extra_claims={name: "x"})  # noqa: S106
    # The control: an extra that names nothing required is carried.
    issued = signer.issue(credential, token_use="agent", extra_claims={"apg_other": 1})  # noqa: S106
    assert _payload(issued.token)["apg_other"] == 1


# ---------------------------------------------------------------------------
# The plane
# ---------------------------------------------------------------------------


def _gated(monkeypatch: Any) -> tuple[Any, list[str]]:
    """The release lock with `create_note` approval-gated, and a recorder."""
    lock, _registry, _recorded = _registered(monkeypatch, "notes:write")
    dialled: list[str] = []

    def capture(*_: Any, **kwargs: Any) -> Any:
        dialled.append(kwargs["idempotency_key"])
        return [{"id": "note-1", "title": "t"}]

    monkeypatch.setattr(mcp_tools, "execute_write", capture)
    return _relocked(lock, "create_note", requires_approval=True), dialled


def _write(lock: Any, *, approval: Any, dry_run: bool = False, key: str = IDEMPOTENCY_KEY) -> Any:
    return mcp_tools.invoke_write(
        lock,
        base_url=BASE,
        token="t",  # noqa: S106 -- a placeholder, not a credential
        request_id=REQUEST_ID,
        tool="create_note",
        arguments={"p_title": "t", "p_content": "c"},
        idempotency_key=key,
        dry_run=dry_run,
        approval=approval,
    )


def _claim(tool: str = "create_note", key: str = IDEMPOTENCY_KEY) -> dict[str, str]:
    return {"id": str(APPROVAL), "tool": tool, "key": key}


def test_the_plane_serves_an_approved_write_for_its_tool_and_key(monkeypatch: Any) -> None:
    """Through `invoke_write`, and through the REGISTERED closure -- which is
    where the claim is read from the verified token, and a closure that passed
    `approval=None` would make every approved step a refusal."""
    lock, dialled = _gated(monkeypatch)
    served = _write(lock, approval=_claim())
    assert served["row_count"] == 1
    assert dialled == [IDEMPOTENCY_KEY]

    from app.mcp_budgets import ReadSlots

    monkeypatch.setattr(mcp_authorization, "current_approval", lambda: _claim())
    registry = _Registry()
    mcp_tools.register(registry, lock, base_url=BASE, slots=ReadSlots(2))
    result = asyncio.run(
        registry.tools["create_note"](
            p_title="t", p_content="c", idempotency_key=IDEMPOTENCY_KEY, dry_run=False
        )
    )
    assert result["row_count"] == 1
    assert dialled == [IDEMPOTENCY_KEY, IDEMPOTENCY_KEY]


def test_the_plane_refuses_a_claim_for_another_tool_or_key(monkeypatch: Any) -> None:
    """The claim authorises ONE write: this tool, this key."""
    lock, dialled = _gated(monkeypatch)
    for claim in (
        _claim(tool="update_task_status"),
        _claim(key="idem-0000000000000002"),
    ):
        with pytest.raises(AgentVisible) as refused:
            _write(lock, approval=claim)
        assert str(refused.value) == REFUSAL_TEXT
    assert dialled == [], "a mismatched claim reached the transport"


def test_the_plane_refuses_an_approved_dry_run(monkeypatch: Any) -> None:
    """D1722: a capability may declare a dry run its SQL does not keep, so an
    approved call is never rehearsed -- refused before anything is sent."""
    lock, dialled = _gated(monkeypatch)
    with pytest.raises(AgentVisible) as refused:
        _write(lock, approval=_claim(), dry_run=True)
    assert refused.value.token == mcp_errors.INPUT_NOT_PERMITTED
    assert "an approved call is not rehearsed" in str(refused.value)
    assert dialled == []


def test_a_token_without_the_claim_is_refused_as_before(monkeypatch: Any) -> None:
    """**The control.** No claim: the same token, the same detail, the same
    reason, nothing dialled -- through the function and through the closure,
    where `current_approval()` answers `None` for every ordinary token."""
    lock, dialled = _gated(monkeypatch)
    with pytest.raises(AgentVisible) as refused:
        _write(lock, approval=None)
    assert str(refused.value) == REFUSAL_TEXT
    assert refused.value.reason == mcp_errors.APPROVAL_REQUIRED_REASON

    from fastmcp.exceptions import ToolError

    from app.mcp_budgets import ReadSlots

    monkeypatch.setattr(mcp_authorization, "current_approval", lambda: None)
    registry = _Registry()
    mcp_tools.register(registry, lock, base_url=BASE, slots=ReadSlots(2))
    with pytest.raises(ToolError) as masked:
        asyncio.run(
            registry.tools["create_note"](
                p_title="t", p_content="c", idempotency_key=IDEMPOTENCY_KEY, dry_run=False
            )
        )
    assert str(masked.value) == REFUSAL_TEXT
    assert dialled == []


def test_a_malformed_claim_is_a_claim_error(monkeypatch: Any) -> None:
    """A malformed claim is not the absence of one: `approval_claim` raises,
    and the plane's reader turns that into `None` -- the ordinary refusal --
    rather than a 500 or a served call."""
    good = {"id": str(APPROVAL), "tool": "create_note", "key": IDEMPOTENCY_KEY}
    assert claims.approval_claim({claims.APPROVAL_CLAIM: good}) == good
    assert claims.approval_claim({}) is None
    for malformed in (
        "a string",
        {"id": str(APPROVAL), "tool": "create_note"},
        {**good, "extra": "x"},
        {**good, "id": "not-a-uuid"},
        {**good, "tool": ""},
        {**good, "key": "short"},
        {**good, "key": 12345678},
    ):
        with pytest.raises(claims.ClaimError):
            claims.approval_claim({claims.APPROVAL_CLAIM: malformed})

    from fastmcp.server import dependencies

    class Granted:
        token = "the.callers.token"  # noqa: S105 -- a placeholder
        claims: ClassVar[dict[str, Any]] = {claims.APPROVAL_CLAIM: {**good, "id": "not-a-uuid"}}

    monkeypatch.setattr(dependencies, "get_access_token", lambda: Granted())
    assert mcp_authorization.current_approval() is None
    Granted.claims = {claims.APPROVAL_CLAIM: good}
    assert mcp_authorization.current_approval() == good
