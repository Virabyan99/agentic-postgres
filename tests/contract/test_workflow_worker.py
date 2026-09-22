"""The loop: the four orderings, the one token, and what it cannot see.

**Nothing here reaches a database, a network or a container.** The repository
is a fake that RECORDS ITS CALLS IN ORDER, the service is a fake whose
`step_token` counts calls and can be made to refuse, and the transport is a
function returning canned bytes -- rig 32b's bytes, framed as the deployed
plane framed them, rather than an envelope written here to match what the
classifier expects. A classifier proved against its author's idea of the wire
format is a classifier proved against a belief.

The load-bearing proofs are the ORDER (claim, mint, call, finish) and the
NEGATIVES: no call after a refused mint, no token outliving the step, no
retry for a terminal token, and no `replayed` assigned by a loop that cannot
see one.
"""

from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from agentic_postgres import REPO_ROOT, runtime_override, service_source

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

worker = service_source.load("workflow_worker")
mcp_upstream = service_source.load("mcp_upstream")
mcp_runtime_path = REPO_ROOT / "services" / "auth-api" / "app" / "mcp_runtime.py"
WORKER_SOURCE = REPO_ROOT / "services" / "auth-api" / "app" / "workflow_worker.py"
MAIN_SOURCE = REPO_ROOT / "services" / "auth-api" / "app" / "main.py"


# ---------------------------------------------------------------------------
# The fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeStep:
    """What `workflow_claim_step` hands back, in `ClaimedStep`'s shape."""

    step_id: UUID = field(default_factory=uuid4)
    run_id: UUID = field(default_factory=uuid4)
    position: int = 1
    name: str = "first"
    attempt: int = 1
    request_id: UUID = field(default_factory=uuid4)
    agent_id: UUID = field(default_factory=uuid4)
    dry_run: bool = False
    step: dict[str, Any] = field(
        default_factory=lambda: {
            "name": "first",
            "tool": "create_note",
            "kind": "write",
            "arguments": {"p_title": "one", "p_content": "two"},
            "retry": {"max": 0, "backoff_seconds": 30},
            "timeout_seconds": 30,
        }
    )
    input: dict[str, Any] = field(default_factory=dict)
    prior: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    idempotency_key: str = "wf-abc-first"


class FakeRepository:
    """Records every call, in order, with its keyword arguments."""

    def __init__(self, steps: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._steps = list(steps or [])

    async def heartbeat(self, **kwargs: Any) -> None:
        self.calls.append(("heartbeat", kwargs))

    async def claim(self, **kwargs: Any) -> Any:
        self.calls.append(("claim", kwargs))
        return self._steps.pop(0) if self._steps else None

    async def finish(self, **kwargs: Any) -> str:
        self.calls.append(("finish", kwargs))
        return "running"

    async def park(self, **kwargs: Any) -> str:
        self.calls.append(("park", kwargs))
        return "parked"

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def one(self, name: str) -> dict[str, Any]:
        found = [arguments for called, arguments in self.calls if called == name]
        assert len(found) == 1, f"{name} was called {len(found)} times"
        return found[0]


@dataclass
class FakeIssued:
    token: str = "a.token.value"  # noqa: S105 -- a literal in a fake, not a credential
    expires_at: int = 0
    token_use: str = "agent"  # noqa: S105 -- a claim discriminator


class FakeService:
    """Counts mints, and can refuse."""

    def __init__(self, refuse: Exception | None = None) -> None:
        self.minted: list[str] = []
        self._refuse = refuse

    async def step_token(self, agent_id: str) -> FakeIssued:
        self.minted.append(agent_id)
        if self._refuse is not None:
            raise self._refuse
        return FakeIssued()


def sse(payload: dict[str, Any]) -> bytes:
    """Rig 32b's framing, verbatim: `event: message\\r\\ndata: {...}\\r\\n\\r\\n`."""
    return f"event: message\r\ndata: {json.dumps(payload)}\r\n\r\n".encode()


OK_RESULT = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "content": [{"type": "text", "text": '{"tool":"create_note","row_count":1}'}],
        "isError": False,
    },
}


def refusal(token: str, detail: str = "a detail") -> dict[str, Any]:
    """A tool refusal, as `AgentVisible.__str__` renders it through the framework."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": f"{token}: {detail}"}], "isError": True},
    }


def drive(
    *,
    step: Any | None = None,
    service: FakeService | None = None,
    send: Any = None,
    monkeypatch: Any,
) -> tuple[FakeRepository, FakeService]:
    """One turn of the loop, with the transport replaced."""
    repository = FakeRepository([step] if step is not None else [])
    used = service or FakeService()
    if send is not None:
        monkeypatch.setattr(worker, "_send", send)
    asyncio.run(
        worker.run_forever(
            repository=repository,
            service=used,
            url="http://mcp:8080/mcp",
            holder="host:1:aa",
            sleep=_never_sleeps,
            once=True,
        )
    )
    return repository, used


async def _never_sleeps(_seconds: float) -> None:
    raise AssertionError("the loop slept in a proof that claims a step")


# ---------------------------------------------------------------------------
# The order
# ---------------------------------------------------------------------------


def test_a_step_is_claimed_then_minted_then_called_then_finished_in_that_order(
    monkeypatch: Any,
) -> None:
    """**The first of the four orderings.** A token is minted for a step this
    loop already holds a lease on; minting first would spend an agent's
    authority on no work at all."""
    seen: list[str] = []

    def send(url: str, token: str, body: bytes, **kwargs: Any) -> tuple[int, bytes]:
        seen.append("call")
        return 200, sse(OK_RESULT)

    service = FakeService()
    original = service.step_token

    async def counted(agent_id: str) -> FakeIssued:
        seen.append("mint")
        return await original(agent_id)

    service.step_token = counted  # type: ignore[method-assign]

    repository, _ = drive(step=FakeStep(), service=service, send=send, monkeypatch=monkeypatch)

    assert repository.names == ["heartbeat", "claim", "finish"]
    assert seen == ["mint", "call"]
    # And the mint happened between the claim and the finish, which the two
    # lists above only show when read together.
    assert repository.names.index("claim") < repository.names.index("finish")


def test_one_token_per_step_attempt_and_none_outlives_the_step(monkeypatch: Any) -> None:
    """**The second ordering**, asserted twice: once by counting, once by AST.

    The count says one mint per step. The AST says the NAME `token` does not
    survive `process` -- every path out of that function deletes it, including
    the ones that raise, which is why the `del` is in a `finally`.
    """
    #: **TWO steps, in one loop.** The first version of this drove one, and the
    #: battery's m1 -- mint once before the loop and reuse the token -- SURVIVED
    #: it: a cache is invisible when there is only ever one call to cache.
    #: "One token for one step" and "one token PER step" are different
    #: sentences, and only the second is the property.
    monkeypatch.setattr(worker, "_send", lambda *a, **k: (200, sse(OK_RESULT)))
    repository = FakeRepository()
    service = FakeService()
    first, second = FakeStep(), FakeStep()
    second.agent_id = first.agent_id
    for step in (first, second):
        asyncio.run(
            worker.process(
                step,
                repository=repository,
                service=service,
                holder="host:1:aa",
                url="http://mcp:8080/mcp",
                now=lambda: 0.0,
            )
        )
    assert len(service.minted) == 2, (
        f"two steps were processed and {len(service.minted)} token(s) were minted; "
        "a token reused across steps is an authority whose lifetime is the "
        "worker's rather than the work's"
    )

    tree = ast.parse(WORKER_SOURCE.read_text(encoding="utf-8"))
    process = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "process"
    )
    deletes = [
        target.id
        for node in ast.walk(process)
        if isinstance(node, ast.Delete)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    assert "token" in deletes, "`process` does not drop the token it minted"

    # The `del` is inside a `finally`, so a raise on the call path drops it too.
    assert any(
        isinstance(node, ast.Try)
        and any(
            isinstance(inner, ast.Delete)
            and any(isinstance(t, ast.Name) and t.id == "token" for t in inner.targets)
            for inner in node.finalbody
        )
        for node in ast.walk(process)
    ), "the token is dropped on the happy path only"


def test_the_call_carries_the_key_the_request_id_and_the_token(monkeypatch: Any) -> None:
    """Three values, three reasons, and none of them is the loop's own.

    The idempotency key is the SUBSTRATE's, derived per (run, step) at enqueue.
    The request id is the CLAIM's, minted per attempt and returned so that both
    sides of the correlation carry one value (D1686). The token is the
    SERVICE's, for the agent whose run this is.
    """
    captured: dict[str, Any] = {}

    def send(url: str, token: str, body: bytes, **kwargs: Any) -> tuple[int, bytes]:
        captured.update(url=url, token=token, body=json.loads(body), **kwargs)
        return 200, sse(OK_RESULT)

    step = FakeStep()
    drive(step=step, send=send, monkeypatch=monkeypatch)

    assert captured["url"] == "http://mcp:8080/mcp"
    assert captured["token"] == "a.token.value"  # noqa: S105
    assert captured["request_id"] == str(step.request_id)
    assert captured["timeout"] == float(step.timeout_seconds)

    body = captured["body"]
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "create_note"
    arguments = body["params"]["arguments"]
    assert arguments["idempotency_key"] == step.idempotency_key
    assert arguments["dry_run"] is False
    assert arguments["p_title"] == "one"


def test_a_successful_call_finishes_the_step_and_the_replay_is_not_the_loops_to_see(
    monkeypatch: Any,
) -> None:
    """**D1671**, and it is a refusal to guess rather than a missing feature.

    `invoke_write` returns `{tool, row_count, row, dry_run}` and returns the
    same row id with `row_count` 1 whether the write committed now or was
    re-read from the idempotency record; the word `replayed` exists only in
    `app_private.agent_audit.outcome`, which the HTTP result does not carry.
    Rig 32c measured it. So the loop finishes `succeeded` and never assigns an
    outcome it cannot determine (ADR 0195).
    """
    repository, _ = drive(
        step=FakeStep(), send=lambda *a, **k: (200, sse(OK_RESULT)), monkeypatch=monkeypatch
    )
    finished = repository.one("finish")
    assert finished["outcome"] == "succeeded"
    assert finished["reason"] is None

    source = WORKER_SOURCE.read_text(encoding="utf-8")
    assert '"replayed"' not in source, (
        "the loop assigns `replayed` somewhere; it cannot see one, and a value "
        "it cannot determine is reported rather than guessed (D1671)"
    )


def test_a_retryable_failure_parks_and_a_final_one_fails_the_run(monkeypatch: Any) -> None:
    """`write_conflict` is the plane's OWN word for a retry instruction.

    Park IS the backoff: the step gets a time and the claim's predicate brings
    it back. Nothing sleeps, so a worker killed during a backoff loses nothing.
    """
    step = FakeStep()
    step.step = {**step.step, "retry": {"max": 2, "backoff_seconds": 45}}
    repository, _ = drive(
        step=step,
        send=lambda *a, **k: (200, sse(refusal("write_conflict"))),
        monkeypatch=monkeypatch,
    )
    parked = repository.one("park")
    assert parked["reason"] == "write_conflict"
    assert "finish" not in repository.names

    # The last attempt fails the run rather than parking forever.
    exhausted = FakeStep()
    exhausted.attempt = 3
    exhausted.step = {**exhausted.step, "retry": {"max": 2, "backoff_seconds": 45}}
    repository, _ = drive(
        step=exhausted,
        send=lambda *a, **k: (200, sse(refusal("write_conflict"))),
        monkeypatch=monkeypatch,
    )
    assert "park" not in repository.names
    finished = repository.one("finish")
    assert finished["outcome"] == "failed"
    assert finished["reason"] == "write_conflict"


def test_a_terminal_refusal_fails_the_run_naming_the_boundary(monkeypatch: Any) -> None:
    """**D1672.** A tool refusal is HTTP 200 with `result.isError`.

    A classifier reading HTTP status would score every refusal as a success.
    These are rig 32b's bytes: the framing, the `isError` member and the
    `"<token>: <detail>"` text `AgentVisible.__str__` produces.
    """
    for token in ("scope_not_held", "budget_exceeded", "input_not_permitted"):
        step = FakeStep()
        step.step = {**step.step, "retry": {"max": 5, "backoff_seconds": 1}}
        repository, _ = drive(
            step=step,
            send=lambda *a, _token=token, **k: (200, sse(refusal(_token))),
            monkeypatch=monkeypatch,
        )
        assert "park" not in repository.names, f"{token} was retried and it is terminal"
        finished = repository.one("finish")
        assert finished["outcome"] == "refused"
        assert finished["reason"] == token


def test_a_refused_mint_stops_the_run_and_makes_no_call(monkeypatch: Any) -> None:
    """The agent stopped being able to act, so nothing is called at all.

    `token_refused` and not `failed`: nothing refused the WORK, and the
    substrate turns it into a run `stopped` with `agent_not_active`, which is
    what an operator acts on differently.
    """
    errors = service_source.load("errors")
    called = False

    def send(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        nonlocal called
        called = True
        return 200, sse(OK_RESULT)

    service = FakeService(refuse=errors.AuthenticationFailed("agent is revoked"))
    repository, _ = drive(step=FakeStep(), service=service, send=send, monkeypatch=monkeypatch)

    assert called is False, "a call was made after the mint was refused"
    finished = repository.one("finish")
    assert finished["outcome"] == "token_refused"
    assert finished["reason"] == "agent is revoked"


def test_a_dry_run_marks_writes_and_leaves_reads_alone(monkeypatch: Any) -> None:
    """`dry_run` is a tool PARAMETER on a write and does not exist on a read.

    `mcp_tools.register_write` requires both it and `idempotency_key`; the read
    closures take neither. A loop that sent them to a read would be refused by
    the framework before the handler.
    """
    captured: list[dict[str, Any]] = []

    def send(url: str, token: str, body: bytes, **kwargs: Any) -> tuple[int, bytes]:
        captured.append(json.loads(body)["params"]["arguments"])
        return 200, sse(OK_RESULT)

    write = FakeStep()
    write.dry_run = True
    repository, _ = drive(step=write, send=send, monkeypatch=monkeypatch)
    assert captured[-1]["dry_run"] is True
    assert repository.one("finish")["outcome"] == "dry_run"

    read = FakeStep()
    read.dry_run = True
    read.step = {
        "name": "second",
        "tool": "query_resource",
        "kind": "read",
        "resource": "notes",
        "arguments": {"limit": 5},
        "retry": {"max": 0, "backoff_seconds": 30},
        "timeout_seconds": 30,
    }
    repository, _ = drive(step=read, send=send, monkeypatch=monkeypatch)
    assert "dry_run" not in captured[-1]
    assert "idempotency_key" not in captured[-1]
    # The compiler resolved the resource and the loop supplies it, because the
    # definition may not name it (D1682).
    assert captured[-1]["resource"] == "notes"
    assert repository.one("finish")["outcome"] == "succeeded", (
        "a read under a dry run is not a dry run: nothing was rolled back"
    )


def test_the_lease_margin_is_a_function_of_the_client_timeout() -> None:
    """Two numbers with one true relationship between them is what goes stale.

    Bound to `mcp_upstream.UPSTREAM_TIMEOUT_SECONDS` -- the PLANE's one
    constant -- and not to `storage_client`'s `CONNECT_`/`READ_` pair, which
    belongs to boto3 and to R2 (D1670).
    """
    assert worker.lease_margin_seconds() == 2 * mcp_upstream.UPSTREAM_TIMEOUT_SECONDS

    # Read from the AST and not from the text. The module's own docstring NAMES
    # `storage_client` to say what it is not reading, and the first spelling of
    # this proof searched the file for the string and failed on that sentence
    # -- which is `_referenced_names`' own recorded reason for being an AST
    # walk (D680: a grep over prose is a filesystem fact standing in for a
    # property).
    tree = ast.parse(WORKER_SOURCE.read_text(encoding="utf-8"))
    reached = {
        ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Attribute | ast.Name)
    }
    assert "mcp_upstream.UPSTREAM_TIMEOUT_SECONDS" in reached
    assert not {name for name in reached if "storage_client" in name}
    assert not {name for name in reached if "CONNECT_TIMEOUT_SECONDS" in name}


def test_the_claim_asks_for_a_margin_and_the_substrate_adds_the_steps_timeout(
    monkeypatch: Any,
) -> None:
    """**D1687.** The loop cannot compute the lease, because the step's own
    timeout arrives in the claim's result."""
    repository, _ = drive(
        step=FakeStep(), send=lambda *a, **k: (200, sse(OK_RESULT)), monkeypatch=monkeypatch
    )
    claimed = repository.one("claim")
    assert claimed == {"holder": "host:1:aa", "lease_margin_seconds": worker.lease_margin_seconds()}


def test_the_loop_stops_before_its_lease_does(monkeypatch: Any) -> None:
    """A step whose margin was spent before the call is `abandoned`, not failed.

    It goes back to `queued` with its attempt already incremented, so the next
    claim takes it -- the retry that costs nothing, because no work was done.
    """
    called = False

    def send(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        nonlocal called
        called = True
        return 200, sse(OK_RESULT)

    monkeypatch.setattr(worker, "_send", send)
    repository = FakeRepository()
    ticks = iter([0.0, 10_000.0, 10_000.0])
    asyncio.run(
        worker.process(
            FakeStep(),
            repository=repository,
            service=FakeService(),
            holder="host:1:aa",
            url="http://mcp:8080/mcp",
            now=lambda: next(ticks),
        )
    )
    assert called is False
    assert repository.one("finish")["outcome"] == "abandoned"


def test_a_transport_failure_is_retryable_and_a_four_hundred_is_not(monkeypatch: Any) -> None:
    """D1661's three retryable causes, and the one the plan got wrong.

    A transport error and a timeout are transient; a 4xx from the plane is not.
    A 5xx is, because it is the plane failing rather than a tool refusing --
    and a tool refusal is a 200, which is the whole of D1672.
    """
    for failure in (OSError("connection reset"), TimeoutError()):
        step = FakeStep()
        step.step = {**step.step, "retry": {"max": 1, "backoff_seconds": 5}}

        def send(*args: Any, _failure: Any = failure, **kwargs: Any) -> tuple[int, bytes]:
            raise _failure

        repository, _ = drive(step=step, send=send, monkeypatch=monkeypatch)
        assert "park" in repository.names, f"{failure!r} was not retried"

    step = FakeStep()
    step.step = {**step.step, "retry": {"max": 1, "backoff_seconds": 5}}
    repository, _ = drive(step=step, send=lambda *a, **k: (404, b"{}"), monkeypatch=monkeypatch)
    assert "park" not in repository.names
    assert repository.one("finish")["outcome"] == "refused"


def test_a_refused_bearer_stops_the_run_rather_than_failing_the_step(
    monkeypatch: Any,
) -> None:
    """401 and 403 are the agent's authority failing, not the step's work.

    Rig 32b measured both from a sibling container: no bearer is 401 and a
    `token_use: access` bearer is 401, each with `www-authenticate`. Treating
    them as a step failure would fail a run for a reason an operator fixes by
    reauthorising rather than by reading a step's reason.
    """
    for status in (401, 403):
        repository, _ = drive(
            step=FakeStep(),
            send=lambda *a, _status=status, **k: (_status, b""),
            monkeypatch=monkeypatch,
        )
        assert repository.one("finish")["outcome"] == "token_refused"


def test_an_unresolvable_reference_fails_the_step_and_makes_no_call(
    monkeypatch: Any,
) -> None:
    """The compiler validated the SHAPE; the input is what it could not see.

    A marker sent upstream as text would reach the reviewed surface as a title
    reading `{{input.title}}`, which is a write nobody asked for.
    """
    called = False

    def send(*args: Any, **kwargs: Any) -> tuple[int, bytes]:
        nonlocal called
        called = True
        return 200, sse(OK_RESULT)

    step = FakeStep()
    step.step = {**step.step, "arguments": {"p_title": "{{input.missing}}", "p_content": "x"}}
    repository, _ = drive(step=step, send=send, monkeypatch=monkeypatch)

    assert called is False
    finished = repository.one("finish")
    assert finished["outcome"] == "failed"
    assert finished["reason"].startswith("input_unresolved:")


def test_a_reference_resolves_with_its_type_intact(monkeypatch: Any) -> None:
    """`{{input.limit}}` over `{"limit": 5}` is the integer 5, not `"5"`.

    A whole-string reference yields the referenced value; one embedded in a
    longer string interpolates its JSON rendering, which is the only thing a
    string can hold.
    """
    captured: list[dict[str, Any]] = []

    def send(url: str, token: str, body: bytes, **kwargs: Any) -> tuple[int, bytes]:
        captured.append(json.loads(body)["params"]["arguments"])
        return 200, sse(OK_RESULT)

    step = FakeStep()
    step.input = {"title": "from the input", "limit": 5}
    step.prior = {"earlier": {"row": {"id": 7}}}
    step.step = {
        **step.step,
        "arguments": {
            "p_title": "{{input.title}}",
            "p_content": "row {{steps.earlier.row}} and limit {{input.limit}}",
        },
    }
    drive(step=step, send=send, monkeypatch=monkeypatch)
    assert captured[-1]["p_title"] == "from the input"
    assert captured[-1]["p_content"] == 'row {"id": 7} and limit 5'


def test_the_heartbeat_is_written_each_poll(monkeypatch: Any) -> None:
    """Written at every poll and not at every claim: a loop that finds nothing
    to do is still alive, and a heartbeat that only moved on work would report
    an idle deployment as a dead one."""
    repository = FakeRepository()
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            worker.run_forever(
                repository=repository,
                service=FakeService(),
                url="http://mcp:8080/mcp",
                holder="host:1:aa",
                sleep=sleep,
            )
        )
    assert repository.names == ["heartbeat", "claim"]
    assert slept == [worker.POLL_SECONDS]


def test_an_exception_in_the_loop_does_not_stop_the_verifier() -> None:
    """**This process's first job is to verify tokens** (ADR 0226).

    A workflow defect that could stop the auth service would make it an
    authentication outage. The supervisor logs and re-enters; `CancelledError`
    is re-raised, because that is the lifespan asking it to stop and swallowing
    it would hang the shutdown.
    """
    entries: list[int] = []

    async def failing(**kwargs: Any) -> None:
        entries.append(len(entries))
        if len(entries) == 1:
            raise RuntimeError("the substrate answered something unexpected")
        raise asyncio.CancelledError

    async def sleep(_seconds: float) -> None:
        return None

    original = worker.run_forever
    worker.run_forever = failing  # type: ignore[assignment]
    try:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(worker.supervise(repository=object(), service=object(), sleep=sleep))
    finally:
        worker.run_forever = original  # type: ignore[assignment]

    assert len(entries) == 2, "the loop was not restarted after it raised"


# ---------------------------------------------------------------------------
# Where the loop runs, and what it is allowed to know
# ---------------------------------------------------------------------------


def test_the_loop_starts_in_auth_mode_only() -> None:
    """An AST scan of `main.py`: `create_task` is reached under `mode == "auth"`.

    Read from the source rather than by building two applications, because
    building one opens a pool. The property is structural -- the task's
    creation is inside a branch on the mode -- and a structural property is
    read structurally.
    """
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    creations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_task"
    ]
    assert len(creations) == 1, f"main.py creates {len(creations)} tasks; this proof reads one"

    guarded = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = ast.unparse(node.test)
        if 'mode == "auth"' not in test and "mode == 'auth'" not in test:
            continue
        if any(creation in ast.walk(node) for creation in creations):
            guarded = True
    assert guarded, 'the workflow task is created outside a branch on `mode == "auth"`'


def test_the_planes_address_is_the_one_the_deploy_publishes() -> None:
    """**D1685.** The loop spells three constants; these are their authorities.

    `src/agentic_postgres` is not in the image and `app.mcp_runtime` pulls in
    the agent framework, so the loop cannot import either. The duplication is
    held HERE, which is the tree's own pattern for a fact that must be true on
    both sides of the image boundary.
    """
    assert worker.PLANE_SERVICE == runtime_override.MCP_SERVICE
    assert worker.PLANE_PORT == runtime_override.MCP_SERVICE_PORT

    # Read as TEXT rather than imported: importing `app.mcp_runtime` builds the
    # agent framework's server, which the auth mode never loads.
    source = mcp_runtime_path.read_text(encoding="utf-8")
    declared = next(
        line.split("=", 1)[1].strip().strip('"')
        for line in source.splitlines()
        if line.startswith("MCP_ROUTE_PATH")
    )
    assert worker.PLANE_PATH == declared
    assert worker.plane_url() == f"http://{runtime_override.MCP_SERVICE}:8080{declared}"


def test_the_two_reference_grammars_accept_the_same_strings() -> None:
    """The compiler refuses what the loop cannot resolve, and both spell it.

    One pattern lives in `src/agentic_postgres/workflow_definition.py` and one
    in the image; a divergence is a definition that installs and then fails at
    run time. Compared over strings rather than over the pattern text, so a
    rewrite that means the same thing is not a failure.
    """
    from agentic_postgres import workflow_definition

    accepted = (
        "{{input.title}}",
        "{{steps.first.row}}",
        "{{input.a_b_1}}",
    )
    refused = (
        "{{ input.title }}",
        "{{steps.first}}",
        "{{INPUT.x}}",
        "{{input}}",
        "{{steps.first.row.deeper}}",
    )
    for text in accepted:
        assert workflow_definition.REFERENCE.fullmatch(text), text
        assert worker.REFERENCE.fullmatch(text), text
    for text in refused:
        assert not workflow_definition.REFERENCE.fullmatch(text), text
        assert not worker.REFERENCE.fullmatch(text), text


def test_the_worker_names_no_banned_transport_and_takes_its_host_from_uname() -> None:
    """`socket` is a banned transport name and the right response was to drop
    the capability, not to find another spelling of it (D1668).

    `os.uname().nodename` is the same fact from a call that cannot open a
    connection -- `storage_cleanup.worker_identity`'s choice and its words.
    """
    source = WORKER_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "socket" not in imported
    assert "os.uname()" in source

    holder = worker.worker_identity()
    assert holder.count(":") == 2, holder
    assert len(holder.split(":")[0]) <= 40
