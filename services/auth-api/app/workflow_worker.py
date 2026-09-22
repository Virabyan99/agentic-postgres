"""The workflow loop: one step at a time, inside the auth process (ADR 0226).

**Four orderings here are correctness, and none of them is arithmetic.**

*Claim before mint.* A token is minted for a step this loop already holds a
lease on. Minting first and then finding nothing to do would spend an agent's
authority on no work at all, and the token would exist for a step that was
never claimed -- an authority with no record of what it was for.

*Mint after claim, and drop at finish.* One token per step ATTEMPT, never one
per loop and never one per run. A token reused across steps is an authority
whose lifetime is the worker's rather than the work's, and a worker that lives
for weeks would be holding an agent's credential for weeks. The attempt is the
unit because a retry re-reads the agent's row: an agent revoked between attempt
one and attempt two is refused at attempt two, which is what makes a revocation
stop a run at its next boundary. `del token` on every path out of `process`,
and an AST proof asserts the name does not outlive the function.

*Call between claim and finish, never inside either.* The tool call is a
network request and the lease -- not a row lock -- is what holds the step across
it (ADR 0104, ADR 0227). A transaction held open across an upstream call is a
lock whose duration is set by that call.

*Stop before the lease does.* If the margin has already been spent by the time
the token is minted, the step is finished `abandoned` and returns to `queued`
with its attempt already incremented -- the next claim takes it. Nothing
happened, so nothing is retried; what is recorded is that a worker held it and
ran out of time, which is the signal that the lease margin is wrong.

**What this loop cannot see.** A REPLAY is invisible in a plane result (D1671,
rig 32c): `invoke_write` returns `{tool, row_count, row, dry_run}` and returns
the same row id with `row_count` 1 whether the write committed now or was
re-read from the idempotency record. The word `replayed` exists only in
`app_private.agent_audit.outcome`. So a successful call is finished
`succeeded`, and `replayed` is left as a value the SUBSTRATE may hold -- ADR
0195's rule: a reader that cannot determine something reports that rather than
assigning the likelier answer.

**A tool refusal is HTTP 200** (D1672, rig 32b). It arrives as
`result.isError: true` with the reason in `result.content[0].text`, formatted
by `AgentVisible.__str__` as `"<token>: <detail>"`. Only a protocol-level
failure carries a JSON-RPC `error` member. A classifier that read HTTP status
would score every refusal as a success, so status is consulted for 401/403
alone -- a refused bearer, which is the agent's authority failing rather than
the step's work.

**This module names `urllib` and not `socket`.** The holder's host comes from
`os.uname().nodename`, exactly as `storage_cleanup.worker_identity` takes it
and for the reason that module records: `socket` is a module that can open a
connection, and buying an exemption for its safe half is how the unsafe half
arrives. `TRANSPORT_ALLOWLIST` grants this module `urllib` by name.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any

from app import mcp_upstream
from app.errors import AuthenticationFailed

log = logging.getLogger("app.workflow_worker")

#: How long the loop waits when a claim finds nothing. Not a tuning knob for
#: throughput: a step becomes claimable either because a run was enqueued or
#: because a park expired, and neither is worth sub-second latency at the cost
#: of a query per second per deployment for the rest of the process's life.
POLL_SECONDS = 5

#: How long the lifespan waits for the loop to finish its current step on the
#: way down.
#:
#: **Below `stop_grace_period`, which is 15 s**, so the container's own stop
#: timer is never the thing that kills this task: a worker killed by Docker
#: mid-call leaves a step leased and finishes nothing, and the step is then
#: only reclaimed when the lease expires. Ten leaves five seconds for the pool
#: to close after the task has stopped, in the order `lifespan`'s docstring
#: requires.
SHUTDOWN_GRACE_SECONDS = 10

#: The tokens the PLANE itself calls transient (D1661). `write_conflict` is a
#: compare-and-swap refusal and `mcp_tools.invoke_write`'s own comment calls it
#: *a retry instruction*; nothing here adds a judgement of its own to the
#: plane's vocabulary.
RETRYABLE_TOKENS = frozenset({"write_conflict"})

#: Where the agent plane answers, from inside the project's own network.
#:
#: **Three constants rather than an import, because the import is impossible**
#: (D1685). `runtime_override.MCP_SERVICE` and `MCP_SERVICE_PORT` live in
#: `src/agentic_postgres`, which is not in this image at all, and
#: `MCP_ROUTE_PATH` lives in `app.mcp_runtime`, which pulls in the whole agent
#: framework and is not loaded in `auth` mode. So the three are spelled here
#: and BOUND by a proof: `test_the_planes_address_is_the_one_the_deploy_
#: publishes` imports all three authorities and requires equality. That is the
#: tree's existing pattern for a fact that must hold on both sides of the image
#: boundary -- `profile.py`, `scopes.py` and `strict_json.py` each say *two
#: enforcement points, one number* and each is held by a guard.
PLANE_SERVICE = "mcp"
PLANE_PORT = 8080
PLANE_PATH = "/mcp"

#: What the loop sends and what it will accept back, measured by rig 32b from a
#: sibling container. The `Accept` value is both media types: the framework
#: frames even a single reply as an SSE event, and a request that accepted only
#: JSON was refused.
PLANE_ACCEPT = "application/json, text/event-stream"
REQUEST_ID_HEADER = "X-Request-Id"

#: The same grammar `agentic_postgres.workflow_definition.REFERENCE` compiles,
#: written a second time for D1685's reason: this module is inside the image and
#: that one is not. They are held together by the definitions they both have to
#: accept -- the compiler REFUSES at `validate` anything this cannot resolve, so
#: a divergence is a definition that installs and then fails at run time, which
#: is what `test_the_two_reference_grammars_accept_the_same_strings` refuses.
REFERENCE = re.compile(r"\{\{(input\.[a-z][a-z0-9_]*|steps\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\}\}")


def plane_url() -> str:
    """`http://mcp:8080/mcp`, assembled from the three constants above."""
    return f"http://{PLANE_SERVICE}:{PLANE_PORT}{PLANE_PATH}"


def lease_margin_seconds() -> int:
    """How much longer than the step's own timeout the lease is taken for.

    A function over the PLANE's timeout constant rather than a number here, for
    `storage_cleanup.lease_margin_seconds`' reason: two numbers with one true
    relationship between them is the shape that goes stale, and a stale margin
    is a lease that expires while a call this worker made is still in flight.

    Twice the upstream timeout, because a tool call is at least two upstream
    requests -- `resolve_agent_context` and then the operation itself
    (`mcp_upstream.py:191-194`) -- and the plane may spend its whole timeout on
    each. `UPSTREAM_TIMEOUT_SECONDS` is the plane's ONE constant; the
    `CONNECT_`/`READ_` pair the plan named belongs to `storage_client` and to
    boto3 (D1670).
    """
    return 2 * mcp_upstream.UPSTREAM_TIMEOUT_SECONDS


def worker_identity() -> str:
    """This loop's holder string: host, pid, and a nonce.

    `os.uname().nodename` and not `socket.gethostname()`, which is
    `storage_cleanup.worker_identity`'s choice and its reason: `socket` is a
    banned transport name in this service and the right response to the ban is
    to drop the capability rather than to find another spelling of it.

    The nonce is what makes a RESTART observable. Two workers on one host with
    the same pid is impossible, but a process restarted into the same pid is
    not, and `workflow_heartbeat` resets `started_at` only when the holder
    CHANGES -- which is the evidence the `worker-restart` rehearsal reads.
    """
    host = os.uname().nodename[:40] or "unknown"
    return f"{host}:{os.getpid()}:{token_hex(4)}"


# ---------------------------------------------------------------------------
# Resolving a step's arguments
# ---------------------------------------------------------------------------


class Unresolvable(Exception):
    """A reference the run's input and prior results cannot satisfy."""


def resolve(value: Any, *, run_input: dict[str, Any], prior: dict[str, Any]) -> Any:
    """Substitute `{{input.<key>}}` and `{{steps.<name>.<field>}}`, per attempt.

    The COMPILER validated the shape of every reference and that no step refers
    forward; what it could not check is whether the run's input carries the key,
    because the input arrives at enqueue. So this is the half that can fail, and
    it fails the step by name rather than sending the marker upstream as text.

    A whole-string reference yields the referenced VALUE with its type intact --
    `{{input.limit}}` over `{"limit": 5}` is the integer 5, not `"5"`. A
    reference embedded in a longer string interpolates its JSON rendering, which
    is the only thing a string can hold.
    """
    if isinstance(value, dict):
        return {key: resolve(item, run_input=run_input, prior=prior) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve(item, run_input=run_input, prior=prior) for item in value]
    if not isinstance(value, str):
        return value

    whole = REFERENCE.fullmatch(value)
    if whole is not None:
        return _lookup(whole.group(1), run_input=run_input, prior=prior)

    def _one(match: Any) -> str:
        found = _lookup(match.group(1), run_input=run_input, prior=prior)
        return found if isinstance(found, str) else json.dumps(found, sort_keys=True)

    return REFERENCE.sub(_one, value)


def _lookup(reference: str, *, run_input: dict[str, Any], prior: dict[str, Any]) -> Any:
    namespace, _, rest = reference.partition(".")
    if namespace == "input":
        if rest not in run_input:
            raise Unresolvable(f"input_unresolved: the run's input has no {rest!r}")
        return run_input[rest]
    step_name, _, field = rest.partition(".")
    result = prior.get(step_name)
    if not isinstance(result, dict):
        raise Unresolvable(f"input_unresolved: {step_name!r} recorded no result to read {field!r}")
    if field not in result:
        raise Unresolvable(f"input_unresolved: {step_name!r}'s result has no {field!r}")
    return result[field]


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------


def _send(
    url: str, token: str, body: bytes, *, request_id: str, timeout: float
) -> tuple[int, bytes]:
    """One HTTP exchange with the plane. `urllib`, as the plane's own client uses.

    Kept separate from `process` so a proof can substitute it, and so that the
    ONE place this module reaches a network is one function a reader can find.
    """
    built = urllib.request.Request(  # noqa: S310 -- a container-local address from three constants
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": PLANE_ACCEPT,
            "Content-Type": "application/json",
            REQUEST_ID_HEADER: request_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(built, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


def sse_payload(body: bytes) -> dict[str, Any] | None:
    """The JSON-RPC message out of an SSE response. The last `data:` line wins.

    The framework frames even a single reply as `event: message\\r\\ndata: {...}`
    (D458, re-measured by rig 32b against the deployed plane), so `json.loads`
    over the whole body raises on a perfectly good answer.
    """
    payload: dict[str, Any] | None = None
    for line in body.decode("utf-8", "replace").splitlines():
        if line.startswith("data: "):
            try:
                parsed = json.loads(line[6:])
            except ValueError:
                return None
            if isinstance(parsed, dict):
                payload = parsed
    return payload


def classify(status: int, body: bytes) -> tuple[str, str, dict[str, Any] | None]:
    """What happened, in this loop's vocabulary: (verdict, reason, result).

    `verdict` is one of `ok`, `retry`, `terminal`, `token`. The ORDER of the
    branches is the finding rig 32b paid for (D1672):

    * 401 and 403 are the bearer being refused, not the step failing. That is
      the agent's authority, so it stops the run the way a refused mint does.
    * Any other non-200 is the plane itself, not a tool: a 5xx is transient and
      anything else is terminal.
    * **At 200, the refusal check comes FIRST.** A tool refusal is a 200 with
      `result.isError`, and a classifier that returned `ok` for every 200 would
      score every refusal as a success.
    * A JSON-RPC `error` member is a protocol failure and is terminal: the
      request was malformed or the method is unknown, and neither improves on
      a retry.
    """
    if status in (401, 403):
        return "token", f"the plane refused the step token with {status}", None
    if status != 200:
        verdict = "retry" if status >= 500 else "terminal"
        return verdict, f"upstream_status_{status}", None

    payload = sse_payload(body)
    if payload is None:
        return "terminal", "the plane's reply could not be parsed", None
    if "error" in payload:
        message = payload["error"]
        detail = message.get("message") if isinstance(message, dict) else None
        return "terminal", f"protocol_error: {detail or 'no message'}", None

    result = payload.get("result")
    if not isinstance(result, dict):
        return "terminal", "the plane's reply carried no result", None
    if result.get("isError"):
        token = _refusal_token(result)
        verdict = "retry" if token in RETRYABLE_TOKENS else "terminal"
        return verdict, token, None
    return "ok", "", result


def _refusal_token(result: dict[str, Any]) -> str:
    """The caller-facing token out of a refusal's text.

    `AgentVisible.__str__` is `f"{self.token}: {self.detail}"`, so the token is
    the text before the first `": "`. A refusal whose text does not have that
    shape is reported as `unclassified_refusal` rather than guessed at: the
    detail may carry a caller value, and a loop that took the whole string as a
    token would put one in `workflow_step.reason` (ADR 0141).
    """
    content = result.get("content")
    text = ""
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = str(content[0].get("text", ""))
    head, separator, _ = text.partition(": ")
    if not separator or not head or " " in head:
        return "unclassified_refusal"
    return head


# ---------------------------------------------------------------------------
# One step
# ---------------------------------------------------------------------------


def call_arguments(step: Any) -> dict[str, Any]:
    """What goes in `params.arguments`, by the step's own kind.

    A relation read's `resource` is added HERE from what the compiler resolved,
    because `query_resource`'s first parameter is the resource and the
    definition may not name it (D1682). A write's `idempotency_key` and
    `dry_run` are tool PARAMETERS and both are required by
    `mcp_tools.register_write` -- they are not headers at this layer, whatever
    they become inside the plane (ADR 0181).
    """
    compiled = step.step
    arguments = dict(
        resolve(compiled.get("arguments") or {}, run_input=step.input, prior=step.prior)
    )
    if compiled.get("kind") == "read" and compiled.get("resource"):
        arguments["resource"] = compiled["resource"]
    if compiled.get("kind") == "write":
        arguments["idempotency_key"] = step.idempotency_key
        arguments["dry_run"] = bool(step.dry_run)
    return arguments


async def process(
    step: Any, *, repository: Any, service: Any, holder: str, url: str, now: Any
) -> None:
    """Mint, call, finish. One step, one token, one outcome.

    `holder` is a parameter rather than a field of `step`, because `ClaimedStep`
    is frozen: the claim's row describes the STEP and the holder is this loop's,
    and attaching one to the other would mean a row carrying a fact the
    database did not answer with.

    `now` is MONOTONIC: the deadline is a duration, and a wall clock stepping
    backwards during an NTP correction would make the worker believe it has
    time it does not (`storage_cleanup.sweep`'s reason).
    """
    started = now()
    deadline = started + step.timeout_seconds

    try:
        issued = await service.step_token(str(step.agent_id))
    except AuthenticationFailed as exc:
        # The agent stopped being able to act. Finished `token_refused`, which
        # the substrate turns into a run `stopped` with `agent_not_active` --
        # not `failed`, because nothing refused the work. **No call is made.**
        await repository.finish(
            step_id=step.step_id,
            holder=holder,
            outcome="token_refused",
            result=None,
            reason=str(exc),
        )
        return

    token = issued.token
    try:
        try:
            arguments = call_arguments(step)
        except Unresolvable as exc:
            await repository.finish(
                step_id=step.step_id,
                holder=holder,
                outcome="failed",
                result=None,
                reason=str(exc),
            )
            return

        if now() >= deadline:
            # The margin was spent before the call began. `abandoned` returns
            # the step to `queued` with its attempt already incremented, so the
            # next claim takes it -- the retry that costs nothing, because no
            # work was done.
            await repository.finish(
                step_id=step.step_id,
                holder=holder,
                outcome="abandoned",
                result=None,
                reason="the lease margin was spent before the call began",
            )
            return

        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": step.step.get("tool"), "arguments": arguments},
            }
        ).encode("utf-8")

        try:
            status, answer = await asyncio.to_thread(
                _send,
                url,
                token,
                body,
                request_id=str(step.request_id),
                timeout=float(step.timeout_seconds),
            )
        except (OSError, TimeoutError) as exc:
            verdict, reason, result = "retry", f"transport: {type(exc).__name__}", None
        else:
            verdict, reason, result = classify(status, answer)
    finally:
        # **Dropped on every path out of this function**, including the ones
        # that raise. An AST proof asserts the name does not outlive `process`.
        del token

    if verdict == "ok":
        outcome = "dry_run" if (step.dry_run and step.step.get("kind") == "write") else "succeeded"
        await repository.finish(
            step_id=step.step_id,
            holder=holder,
            outcome=outcome,
            result=json.dumps(result, default=str),
            reason=None,
        )
        return

    if verdict == "token":
        await repository.finish(
            step_id=step.step_id,
            holder=holder,
            outcome="token_refused",
            result=None,
            reason=reason,
        )
        return

    if verdict == "retry" and step.attempt <= int(step.step.get("retry", {}).get("max", 0)):
        # **Park IS the backoff** (ADR 0227). Nothing sleeps: the step gets a
        # time and the claim's own predicate brings it back. `attempt` was
        # incremented BY the claim, so `attempt <= max` means "there is another
        # attempt after this one".
        backoff = int(step.step.get("retry", {}).get("backoff_seconds", 30))
        await repository.park(
            step_id=step.step_id,
            holder=holder,
            reason=reason,
            resume_after=datetime.now(UTC) + timedelta(seconds=backoff),
        )
        return

    await repository.finish(
        step_id=step.step_id,
        holder=holder,
        outcome="failed" if verdict == "retry" else "refused",
        result=None,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


async def run_forever(
    *,
    repository: Any,
    service: Any,
    url: str | None = None,
    holder: str | None = None,
    now: Any = time.monotonic,
    sleep: Any = asyncio.sleep,
    once: bool = False,
) -> None:
    """Heartbeat, claim, process. Forever, or once for a proof.

    The heartbeat is written at every poll and not at every claim: a loop that
    finds nothing to do is still alive, and a heartbeat that only moved on work
    would report an idle deployment as a dead one.

    **The MARGIN is what this loop passes; the substrate adds the step's own
    timeout** (D1687). The lease ends up as `step.timeout_seconds +
    lease_margin_seconds()` -- long enough for the call this worker is about to
    make plus the plane's own worst case, and no longer, because a lease is how
    long a dead worker's step stays unclaimable. The step's timeout arrives in
    the claim's own result, so this side cannot compute the sum.
    """
    address = url or plane_url()
    identity = holder or worker_identity()
    while True:
        await repository.heartbeat(holder=identity)
        step = await repository.claim(
            holder=identity,
            lease_margin_seconds=lease_margin_seconds(),
        )
        if step is None:
            if once:
                return
            await sleep(POLL_SECONDS)
            continue

        await process(
            step,
            repository=repository,
            service=service,
            holder=identity,
            url=address,
            now=now,
        )
        if once:
            return


async def supervise(
    *, repository: Any, service: Any, sleep: Any = asyncio.sleep, url: str | None = None
) -> None:
    """Restart the loop when it raises, and never take the verifier with it.

    **This process's first job is to verify tokens** (ADR 0226). A worker that
    could stop the auth service would make a workflow defect an authentication
    outage, so every exception short of cancellation is logged and the loop is
    entered again after one poll interval.

    `CancelledError` is re-raised rather than caught: it is the lifespan asking
    this task to stop, and a supervisor that swallowed it would hang the
    shutdown until the grace period killed the container.
    """
    while True:
        try:
            await run_forever(repository=repository, service=service, url=url)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("the workflow loop raised; restarting it")
            await sleep(POLL_SECONDS)
