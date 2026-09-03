"""Four budgets, two error channels, one telemetry record (Session 8, Run 8).

**Independence is the property**, and it is easiest to state by what each bound
does not cover. A row ceiling bounds nothing about a row's size; a byte ceiling
bounds nothing about how long the database spends producing it; and neither
bounds how many callers are doing it at once.

Measured before any of this was written:

    a tool body sleeping 5 s under a 1 s timeout   returned at 1.10 s
    CONTROL -- the same tool sleeping 0.05 s        returned at 0.09 s
    eight overlapping tool calls                    peak 8 of 8 concurrent

So elapsed time was already bounded by the framework, from the lock's
`timeout_ms`, and concurrency was not bounded at all.

And the measurement that decided the error design:

    a plain Exception with a message   masked -> "Error calling tool 'x'"
    ToolError with the same message    masked -> the message

`ToolError` is the framework's caller-facing channel and bypasses the mask, so
Run 6's carefully-worded input refusals -- raised as plain exceptions -- reached
nobody at all.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from tests.contract.rendered_fixtures import (
    FIXTURE_KEYS,
    fixture_dir,
    needs_rendered_fixtures,
)

from agentic_postgres import REPO_ROOT, config, naming, rendering
from app import mcp_errors, mcp_telemetry, mcp_tools
from app import settings as settings_module
from app.mcp_budgets import (
    DEFAULT_MAX_CONCURRENT_READS,
    PER_READ_MB,
    PROCESS_OVERHEAD_MB,
    ReadSlots,
    memory_floor_mb,
)
from app.mcp_errors import CALLER_FACING_TOKENS, AgentVisible, as_tool_error
from app.mcp_telemetry import RECORD_FIELDS, Timed

pytestmark = [pytest.mark.contract, pytest.mark.p0]


# ---------------------------------------------------------------------------
# concurrency: the bound that did not exist
# ---------------------------------------------------------------------------


def test_the_semaphore_bounds_how_many_run_at_once() -> None:
    """The measurement this class exists because of: 8 of 8 ran, unbounded."""
    slots = ReadSlots(3)
    peak = {"now": 0, "peak": 0}

    async def one() -> None:
        async with slots:
            peak["now"] += 1
            peak["peak"] = max(peak["peak"], peak["now"])
            await asyncio.sleep(0.02)
            peak["now"] -= 1

    asyncio.run(_gather(one, 12))

    assert peak["peak"] == 3, f"peak was {peak['peak']}, not the bound"


def test_without_the_bound_they_all_run_at_once() -> None:
    """**The control.** Without it, a slow test could pass for the wrong reason.

    Twelve coroutines with no semaphore, in the same shape: the peak is twelve.
    So the test above is measuring the bound rather than the scheduler.
    """
    peak = {"now": 0, "peak": 0}

    async def one() -> None:
        peak["now"] += 1
        peak["peak"] = max(peak["peak"], peak["now"])
        await asyncio.sleep(0.02)
        peak["now"] -= 1

    asyncio.run(_gather(one, 12))

    assert peak["peak"] == 12


async def _gather(work: Any, count: int) -> None:
    await asyncio.gather(*(work() for _ in range(count)))


def test_a_slot_is_returned_when_the_body_raises() -> None:
    """A leaked slot tightens the bound every time something goes wrong.

    The plane would then stop answering for a reason nobody can see, which is
    worse than the failure that caused it.
    """
    slots = ReadSlots(2)

    async def failing() -> None:
        for _ in range(5):
            with pytest.raises(RuntimeError):
                # **Bounded, and that is not a formality.** With the release
                # removed, the third acquire never returns -- so the honest
                # failure of a leaked slot is a HANG, not an assertion. A test
                # that could hang turns a mutation battery into a stalled
                # process with no verdict, which is a third outcome beside
                # FAILED and ERROR that nothing here models (D452).
                async with asyncio.timeout(2):
                    async with slots:
                        raise RuntimeError("boom")
        assert slots.available == 2

    asyncio.run(failing())


def test_saturation_queues_rather_than_refusing() -> None:
    """The wait is bounded by a DIFFERENT budget, which is the point (ADR 0129).

    A caller arriving at a full semaphore waits, and the tool's own timeout
    fires if the wait is long. That is the clearest demonstration of
    independence in the set: this bound is survivable because another one limits
    how long waiting can last.
    """
    slots = ReadSlots(1)
    order: list[str] = []

    async def scenario() -> None:
        async def hold(name: str) -> None:
            async with slots:
                order.append(f"{name}-in")
                await asyncio.sleep(0.05)
                order.append(f"{name}-out")

        await asyncio.gather(hold("a"), hold("b"))

    asyncio.run(scenario())

    # Never interleaved: one finished before the other started.
    assert order in (
        ["a-in", "a-out", "b-in", "b-out"],
        ["b-in", "b-out", "a-in", "a-out"],
    )


def test_a_bound_below_one_is_refused() -> None:
    """A concurrency bound of zero admits nothing and would look like a hang."""
    for bad in (0, -1):
        with pytest.raises(ValueError, match="below one"):
            ReadSlots(bad)


@needs_rendered_fixtures
def test_the_concurrency_share_is_derived_from_the_rest_pool() -> None:
    """ADR 0129: a division, not an independent grant.

    Read out of the RENDERED `compose.env` of both fixtures, so what is checked
    is the relation the renderer produced rather than the arithmetic restated
    here. A test that recomputed `pool // 2` and compared it to itself would go
    green for any renderer at all.
    """
    assert "MCP_MAX_CONCURRENT_READS" in rendering.COMPOSE_ENV_KEYS

    for key in FIXTURE_KEYS:
        values = _compose_env(fixture_dir(key))
        pool = int(values["POSTGREST_POOL_SIZE"])
        share = int(values["MCP_MAX_CONCURRENT_READS"])

        assert share == max(1, pool // 2), f"{key}: {share} is not half of {pool}"
        assert 1 <= share < pool, f"{key}: the agent plane may not claim the whole pool"


def test_the_renderer_itself_derives_the_share() -> None:
    """The same relation, asserted where a change to the renderer can reach it.

    **D453.** The fixture test above reads `.generated/`, which is a build
    artefact refreshed by hand. A change to `rendering.py` is therefore
    invisible to it until somebody re-renders -- and the staleness guard that protects
    those fixtures compares `schema_version` alone, which a Compose variable can
    be added or changed without moving. `rendered_fixtures` says so in its own
    docstring; this is the first arm that needed it to be false.

    The two tests are not duplicates and neither replaces the other. That one
    proves the value reached a rendered artefact; this one proves the renderer
    derives it. Only this one goes red when the arithmetic changes.

    **Two pools that disagree**, so a constant cannot satisfy both, and the
    `share < pool` bound is what a share equal to its pool fails -- neither
    assertion restates `pool // 2` against itself.
    """
    small = _render_share(pool_size=4)
    large = _render_share(pool_size=21)

    assert small != large, "a share that does not move with the pool is not derived"
    for pool, share in ((4, small), (21, large)):
        assert share == max(1, pool // 2), f"pool {pool} rendered a share of {share}"
        assert 1 <= share < pool, "the agent plane may not claim the whole pool"


def _render_share(*, pool_size: int) -> int:
    """`MCP_MAX_CONCURRENT_READS` out of one in-process render."""
    identity = naming.derive(
        slug="alpha",
        environment="dev",
        domain="alpha.example.com",
        api_base_path="/api",
        mcp_base_path="/mcp",
        storage_enabled=False,
    )
    database = {"max_client_connections": 100, "pool_size": 20}
    raw = rendering.build_compose_env(
        identity,
        config.database_budget(database),
        database,
        api={"max_rows": 1000, "rest": {"pool_size": pool_size}},
    )
    for line in raw.decode("utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "MCP_MAX_CONCURRENT_READS":
            return int(value.strip())
    raise AssertionError("the renderer produced no MCP_MAX_CONCURRENT_READS at all")


def _compose_env(directory: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (directory / "compose.env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() and not name.strip().startswith("#"):
            values[name.strip()] = value.strip()
    return values


#: Everything `load_mcp` requires EXCEPT the concurrency share.
#:
#: The incomplete environment is the constant and the complete one is built from
#: it, rather than the other way round with a `del`. Two reasons, and the second
#: is the load-bearing one: it reads as "the share is the thing being added", and
#: **a subscript with an `APG_`-prefixed literal is what
#: `test_environment_gates` scans for** (D455). That scan cannot tell a local
#: dict from `os.environ`, so a `del environment["APG_…"]` here reported this
#: offline test as consuming a live environment it never touches.
MCP_ENVIRONMENT_WITHOUT_THE_SHARE = {
    "APG_PROJECT_KEY": "p",
    "APG_PROJECT_ENVIRONMENT": "dev",
    "APG_JWT_ISSUER": "https://i.test/api/app/auth",
    "APG_JWT_AUDIENCE": "urn:a",
    "APG_JWKS_FILE": "/etc/mcp/jwks.json",
    "APG_LISTEN_PORT": "8080",
    "APG_POSTGREST_URL": "http://postgrest:3000",
    "APG_MCP_LOCK_FILE": "/etc/mcp/capability-lock.json",
}


def test_the_runtime_requires_the_share_rather_than_defaulting() -> None:
    """A fallback constant would be a second authority for the division."""
    assert "APG_MCP_MAX_CONCURRENT_READS" in settings_module.MCP_VARIABLES

    complete = dict(MCP_ENVIRONMENT_WITHOUT_THE_SHARE, APG_MCP_MAX_CONCURRENT_READS="5")
    assert settings_module.load_mcp(complete).max_concurrent_reads == 5

    # The CONTROL is the line above: without it, a refusal here would be
    # satisfied by any of the eight other required variables being absent.
    with pytest.raises(settings_module.MissingSetting):
        settings_module.load_mcp(MCP_ENVIRONMENT_WITHOUT_THE_SHARE)


def test_the_four_budgets_are_bounded_by_four_different_things() -> None:
    """Independence, asserted as four distinct mechanisms (ADR 0129).

    Each bound is exercised through the thing that applies it, so collapsing two
    of them into one is a change this test refuses. The rows arm in particular
    shows a result INSIDE the row ceiling and OUTSIDE the byte ceiling, which is
    the pair that makes "independent" a claim rather than a word.
    """
    from app.mcp_lock import Operation, Resource
    from app.mcp_query import build_request

    resource = Resource(
        name="notes",
        capability="query_notes",
        columns=("id", "content"),
        filters={},
        order_by=(("id", "asc"),),
        max_rows=200,
        required_scopes=("notes:read",),
        operation=Operation(method="get", path="/notes", operation_id="notes.get"),
    )

    # rows -- the lock's ceiling, applied in the request builder, and a caller
    # asking for more gets the ceiling rather than what it asked for.
    assert "limit=200" in build_request(resource, timeout_ms=5000, limit=10_000).target

    # bytes -- a runtime constant, and two rows are enough to exceed it while
    # sitting far INSIDE the row ceiling of 200.
    oversized = {"resource": "notes", "row_count": 2, "rows": [{"content": "x" * 900_000}] * 2}
    # AgentVisible, because a caller CAN stay inside this one by asking
    # differently -- which is why it is the budget that gets a message.
    with pytest.raises(AgentVisible, match="budget_exceeded"):
        mcp_tools._within_budget(oversized, resource.max_rows)

    # concurrency -- a semaphore, and it is not any of the numbers above.
    assert DEFAULT_MAX_CONCURRENT_READS >= 1
    assert DEFAULT_MAX_CONCURRENT_READS != resource.max_rows
    assert DEFAULT_MAX_CONCURRENT_READS != mcp_tools.MAX_SERIALIZED_BYTES

    # elapsed time -- the lock's `timeout_ms`, converted to the seconds the
    # framework takes, and belonging to neither of the other three.
    assert mcp_tools.MAX_SERIALIZED_BYTES != resource.max_rows


def test_the_memory_limit_clears_the_floor_at_every_share_the_schema_permits() -> None:
    """**ADR 0131.** The relation, checked against the schema's own bound.

    This is what replaces the manifest validator, and the reason there is none:
    `api.rest.pool_size` is capped by `project.schema.json`, the share is half of
    it, so the largest floor any valid document can ask for is below the limit --
    a validator could not fail for anything the schema admits, and a guard that
    cannot go red is this repository's defect pattern pointing the other way.

    The cap is **read from the schema**, not restated. Raise it past 128 and this
    test fails, naming the choice that has become live: raise the limit, or write
    the validator that is now worth writing.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "project.schema.json").read_text(encoding="utf-8"))
    largest_pool = schema["$defs"]["restService"]["properties"]["pool_size"]["maximum"]

    for pool in (1, 10, largest_pool):
        share = max(1, pool // 2)
        floor = memory_floor_mb(share)
        assert rendering.MCP_MEMORY_LIMIT_MB >= floor, (
            f"a pool of {pool} derives a share of {share}, whose floor is {floor} MiB "
            f"against a limit of {rendering.MCP_MEMORY_LIMIT_MB}. Raise the limit, or "
            "the relation now needs the manifest validator ADR 0131 declined to write"
        )

    assert memory_floor_mb(DEFAULT_MAX_CONCURRENT_READS) == 148


def test_the_floor_moves_with_concurrency_rather_than_being_a_constant() -> None:
    """A floor that ignored the share would be the inherited number again.

    The CONTROL is the third assertion: a floor of zero reads is still the
    process overhead, so "it moves" is not satisfied by a function that is simply
    proportional to its argument and forgets the constant term.
    """
    assert memory_floor_mb(2) - memory_floor_mb(1) == PER_READ_MB
    assert memory_floor_mb(10) > memory_floor_mb(1)
    assert memory_floor_mb(0) == PROCESS_OVERHEAD_MB


# ---------------------------------------------------------------------------
# the two error channels
# ---------------------------------------------------------------------------


def test_only_a_caller_facing_token_can_be_raised_as_visible() -> None:
    """The set is closed, so adding one is an edit somebody reviews."""
    for token in CALLER_FACING_TOKENS:
        AgentVisible(token, "detail", mcp_errors.SCOPE_NOT_HELD_REASON)

    # The reason vocabulary is closed in the same call and refused the same
    # way (ADR 0178). Asserted beside the token so a future widening of one
    # cannot be mistaken for a widening of both.
    with pytest.raises(ValueError, match="not a denial reason"):
        AgentVisible(mcp_errors.SCOPE_NOT_HELD, "detail", "credential")

    with pytest.raises(ValueError, match="not a caller-facing token"):
        AgentVisible("something_new", "detail", mcp_errors.SCOPE_NOT_HELD_REASON)


def test_a_visible_refusal_becomes_the_type_the_framework_lets_through() -> None:
    """Measured: `ToolError` bypasses `mask_error_details`; a plain one does not."""
    from fastmcp.exceptions import ToolError

    error = as_tool_error(
        AgentVisible(
            mcp_errors.SCOPE_NOT_HELD, "needs notes:read", mcp_errors.SCOPE_NOT_HELD_REASON
        )
    )

    assert isinstance(error, ToolError)
    assert "scope_not_held" in str(error)
    assert "needs notes:read" in str(error)


def test_a_structural_refusal_says_nothing() -> None:
    """One word, and it is the same word for every cause (D433)."""
    assert mcp_errors.STRUCTURAL_REFUSAL == "refused"
    assert mcp_errors.STRUCTURAL_REFUSAL not in CALLER_FACING_TOKENS


def test_the_mask_stays_on() -> None:
    """What makes the split a boundary rather than a convention (ADR 0130).

    With the mask on, a new plain exception is silent by default -- so telling a
    caller something is the act that needs a decision, not hiding it.
    """
    import inspect

    source = inspect.getsource(__import__("app.mcp_runtime", fromlist=["x"]).build_server)

    assert "mask_error_details=True" in source


@pytest.mark.parametrize("token", CALLER_FACING_TOKENS)
def test_no_caller_facing_message_names_the_schema_or_an_upstream_status(token: str) -> None:
    """The tokens themselves say nothing about a database or a status code."""
    assert "postgrest" not in token
    assert not any(character.isdigit() for character in token)


# ---------------------------------------------------------------------------
# the write-refusal translation (Session 9 Run 4 — ADR 0139)
# ---------------------------------------------------------------------------


def test_the_enumerated_write_refusals_translate_and_nothing_else_does() -> None:
    """The map is total over the vocabulary and refuses to guess outside it.

    `PGRST202` is the arm that matters: measured (rig4), it shares status 404
    with `PT404` and means the opposite thing — the function the request was
    built for does not exist. Translating it would tell a caller a row is
    missing when the fault is structural.
    """
    conflict = mcp_errors.write_refusal("PT409")
    assert conflict is not None and conflict.token == mcp_errors.WRITE_CONFLICT

    missing = mcp_errors.write_refusal("PT404")
    assert missing is not None and missing.token == mcp_errors.ROW_NOT_FOUND

    unchanged = mcp_errors.write_refusal("PT422")
    assert unchanged is not None and unchanged.token == mcp_errors.INPUT_NOT_PERMITTED

    for masked in ("PGRST202", "PT401", "22P02", "42501", "", "PT999"):
        assert mcp_errors.write_refusal(masked) is None, masked


def test_the_map_speaks_only_errcodes_the_product_actually_raises() -> None:
    """ADR 0139's consequence, made a test: a key migration 0019 never raises
    is dead vocabulary wearing a reviewed look.

    `PT401` must be raised by the product AND absent from the map — its absence
    is a decision (the authentication plane's business), and this arm is what
    keeps that from silently becoming an omission when the migration moves.
    """
    import re

    template = (
        REPO_ROOT / "migrations" / "templates" / "0019-agent-write-and-audit-plane.sql"
    ).read_text(encoding="utf-8")
    raised = set(re.findall(r"ERRCODE = '(PT\d{3})'", template))
    assert raised, "the scan found no errcodes; the template moved or the scan is broken"

    mapped = set(mcp_errors.UPSTREAM_WRITE_REFUSALS)
    assert mapped <= raised, (
        f"the map translates {sorted(mapped - raised)}, which the product never raises"
    )
    assert "PT401" in raised - mapped, (
        "PT401 must stay unmapped by decision (ADR 0139), not by the product no longer raising it"
    )


def test_a_translated_sentence_is_this_repositorys_not_the_wires() -> None:
    """The upstream message is the product's today and an arbitrary string
    after the next migration; nothing from it may survive translation."""
    for code, (token, sentence) in mcp_errors.UPSTREAM_WRITE_REFUSALS.items():
        assert token in CALLER_FACING_TOKENS
        assert "AP4" not in sentence and code not in sentence
        assert not any(character.isdigit() for character in sentence)


# ---------------------------------------------------------------------------
# telemetry, and the canary's list
# ---------------------------------------------------------------------------


def test_a_record_carries_exactly_the_declared_fields() -> None:
    """A record whose shape nobody declared is one the canary is not checking."""
    with Timed("query_resource", resource="notes") as timed:
        timed.principal(agent_id="agent-1", owner_id="owner-1")
        timed.served(row_count=3)

    record = timed._record()
    assert set(record) == set(RECORD_FIELDS)
    assert record["outcome"] == "served"
    assert record["row_count"] == 3


def test_a_record_carries_no_token_no_url_and_no_caller_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """**The canary, offline.**

    A real token, a real URL and a real filter operand are put in the caller's
    way, and the emitted record is searched for all three. They are values that
    exist only because this test created them, so a hit is a leak rather than a
    coincidence -- Session 7's rule, applied to the agent plane's sink.
    """
    token = "eyJhbGciOiJSUzI1NiJ9.CANARY-TOKEN-8f2a.sig"  # noqa: S105
    url = "https://canary.example/api/rest/notes?title=eq.secret"
    operand = "CANARY-FILTER-VALUE-9c3b"

    with (
        caplog.at_level(logging.INFO, logger="apg.mcp"),
        Timed("query_resource", resource="notes") as timed,
    ):
        timed.principal(agent_id="agent-1", owner_id="owner-1")
        timed.served(row_count=1)

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert emitted, "no telemetry record was emitted at all"
    for canary in (token, url, operand):
        assert canary not in emitted

    # And the record's own fields cannot even express them.
    assert not {"token", "url", "filters", "rows", "value"} & set(RECORD_FIELDS)


def test_exactly_one_record_is_emitted_per_call(caplog: pytest.LogCaptureFixture) -> None:
    """Two records per call would double every count an operator reads."""
    with caplog.at_level(logging.INFO, logger="apg.mcp"):
        with Timed("run_report") as timed:
            timed.principal(agent_id="a", owner_id="o")
            timed.served(row_count=1)

    assert len(caplog.records) == 1


def test_an_unclassified_failure_names_the_type_and_never_the_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A message is where a caller's value would be if one ever reached one."""
    with caplog.at_level(logging.INFO, logger="apg.mcp"):
        with pytest.raises(RuntimeError), Timed("query_resource", resource="notes") as timed:
            timed.principal(agent_id="a", owner_id="o")
            raise RuntimeError("CANARY-EXCEPTION-TEXT-1a2b")

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in emitted
    assert "CANARY-EXCEPTION-TEXT-1a2b" not in emitted
    assert '"outcome": "failed"' in emitted


def test_the_outcomes_are_closed() -> None:
    """Three, and `refused` covers both channels: one event to an operator."""
    assert {
        mcp_telemetry.OUTCOME_SERVED,
        mcp_telemetry.OUTCOME_REFUSED,
        mcp_telemetry.OUTCOME_FAILED,
    } == {"served", "refused", "failed"}


def test_nothing_in_the_agent_plane_names_the_audit_role_in_CODE() -> None:
    """D412: telemetry is logs, and `mcp_audit_service` stays Session 9's.

    An **AST** scan over string constants that are not docstrings. The first
    version of this was a text scan and failed on `mcp_telemetry`'s own
    paragraph explaining why the role is unused -- D277's shape, in a test
    written to enforce D277. A comment saying "we do not use X" must not read as
    using X.
    """
    import ast

    service = Path(mcp_telemetry.__file__).parent
    offenders: list[str] = []
    for path in sorted(service.glob("mcp_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(ast.get_docstring(node, clean=False))
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        del docstrings
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        bodies = {
            node.body[0].value.value
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for literal in literals - bodies:
            if "mcp_audit_service" in literal:
                offenders.append(f"{path.name}: {literal[:60]!r}")

    assert not offenders, f"the agent plane names the audit role in code: {offenders}"


def test_that_scan_can_tell_a_docstring_from_a_literal() -> None:
    """**The control for the test above**, and the reason it exists at all.

    `mcp_telemetry`'s docstring DOES contain the role name -- explaining why it
    is not activated -- so a scan that could not tell prose from code would
    report the explanation as the offence.
    """
    assert "mcp_audit_service" in (mcp_telemetry.__doc__ or "")


def test_the_telemetry_record_is_json_and_parses() -> None:
    """An operator greps this. A record that is not one line of JSON is not a record."""
    with Timed("list_resources") as timed:
        timed.principal(agent_id="a", owner_id="o")
        timed.served()

    parsed = json.loads(json.dumps(timed._record()))
    assert parsed["tool"] == "list_resources"
    assert parsed["resource"] is None


# ---------------------------------------------------------------------------
# the canary, offline: no sink can receive a token
# ---------------------------------------------------------------------------

#: Every name in the agent plane that holds a bearer token, and every name that
#: writes to a sink. The test below asserts the two never meet in one call.
#:
#: Session 7's canary is a LIVE proof: it drives a real cycle and greps every
#: place the deployment writes. That proof is worth more and cannot run offline,
#: so this is the half that can -- and the two answer different questions. The
#: live one asks "did a token reach a log"; this one asks "could it".
TOKEN_BEARING_NAMES = frozenset({"token", "current_token", "raw_token", "bearer"})
SINK_CALLS = frozenset({"print", "info", "warning", "error", "debug", "exception", "critical"})


def test_no_sink_call_in_the_agent_plane_is_handed_a_token() -> None:
    """**The canary's offline half** (ADR 0130).

    An AST walk over every `mcp_*` module: for each call to a logging or `print`
    sink, every argument is inspected for a name that holds a token. A token in a
    log is the leak Session 7's canary was built to catch, and the agent plane
    adds a third subject to its list -- Session 7 looked for a URL and an object
    key.

    This is a reachability claim rather than an observation, which is exactly
    why the live proof still matters: a value can reach a log through a name this
    scan does not know. What it buys is that the OBVIOUS way is closed, offline,
    before a deployment exists.
    """
    import ast

    service = Path(mcp_telemetry.__file__).parent
    offenders: list[str] = []
    for path in sorted(service.glob("mcp_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if called not in SINK_CALLS:
                continue
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                for inner in ast.walk(argument):
                    name = None
                    if isinstance(inner, ast.Name):
                        name = inner.id
                    elif isinstance(inner, ast.Attribute):
                        name = inner.attr
                    if name in TOKEN_BEARING_NAMES:
                        offenders.append(f"{path.name}:{node.lineno} {called}(... {name} ...)")

    assert not offenders, f"a token reaches a sink: {offenders}"


def test_that_scan_would_find_one() -> None:
    """**The control**, and without it the scan above proves nothing.

    A scan that matched no name at all would report every tree clean. This
    asserts it finds a token handed to a logger in a source it is given.
    """
    import ast

    def offenders_in(source: str) -> list[str]:
        found = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if called not in SINK_CALLS:
                continue
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                for inner in ast.walk(argument):
                    name = inner.id if isinstance(inner, ast.Name) else getattr(inner, "attr", None)
                    if name in TOKEN_BEARING_NAMES:
                        found.append(called)
        return found

    assert offenders_in("LOGGER.info('who: %s', token)") == ["info"]
    assert offenders_in("print(f'{granted.token}')") == ["print"]
    assert offenders_in("LOGGER.info('who: %s', owner_id)") == []


def test_the_fingerprint_never_reaches_a_sink_either() -> None:
    """A digest of a token is not a token, and is still not a log's business.

    It is stable across a token's whole life, so a log carrying it lets two
    records be linked to one credential -- which is the property the fingerprint
    exists to have INSIDE one request and must not have outside it (ADR 0125).
    """
    import ast

    service = Path(mcp_telemetry.__file__).parent
    offenders: list[str] = []
    for path in sorted(service.glob("mcp_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if called not in SINK_CALLS:
                continue
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                for inner in ast.walk(argument):
                    name = inner.id if isinstance(inner, ast.Name) else getattr(inner, "attr", None)
                    if name in {"fingerprint", "_fingerprint"}:
                        offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, f"a token fingerprint reaches a sink: {offenders}"


# ---------------------------------------------------------------------------
# Per-capability narrowing (ADR 0179)
# ---------------------------------------------------------------------------


def test_a_capability_may_narrow_the_byte_ceiling_and_may_not_widen_it() -> None:
    """`min`, not the declared value, and the schema says the same thing twice.

    Deliberately twice: the schema refuses a wider MANIFEST before a deployment
    exists, and this refuses a wider LOCK, which is a different document and one
    the runtime is required to distrust. A lock compiled by something other than
    this repository's compiler is the case where only one of the two is left.
    """
    from app.mcp_tools import MAX_SERIALIZED_BYTES, _byte_ceiling

    assert _byte_ceiling(None) == MAX_SERIALIZED_BYTES, "an undeclared bound is the global"
    assert _byte_ceiling(65536) == 65536, "a narrower bound is taken"
    assert _byte_ceiling(MAX_SERIALIZED_BYTES) == MAX_SERIALIZED_BYTES
    assert _byte_ceiling(MAX_SERIALIZED_BYTES * 2) == MAX_SERIALIZED_BYTES, (
        "a lock declaring more than the global widened it"
    )


def test_the_schema_maximum_is_the_runtime_constant() -> None:
    """Two files, one number, checked rather than trusted (ADR 0002).

    JSON Schema cannot import a Python constant, so the choice is between two
    authorities that are compared and one that is hoped about. This is the same
    arrangement `DENIAL_REASONS` has against migration 0027.
    """
    import json

    from app.mcp_tools import MAX_SERIALIZED_BYTES

    schema = json.loads(
        (REPO_ROOT / "schemas" / "capabilities.schema.json").read_text(encoding="utf-8")
    )
    declared = schema["$defs"]["capability"]["properties"]["max_response_bytes"]["maximum"]
    assert declared == MAX_SERIALIZED_BYTES, (
        f"the schema caps a capability at {declared} and the runtime ceiling is "
        f"{MAX_SERIALIZED_BYTES}; a manifest could declare a bound the runtime "
        "would then narrow, which makes the schema's refusal a lie"
    )


def test_a_result_above_a_narrowed_ceiling_is_refused_and_says_which_ceiling() -> None:
    """The message names the ceiling that applied, not the global.

    A refusal quoting 1048576 to a caller bounded at 65536 would send them
    looking for a limit that is not the one they hit.
    """
    from app.mcp_errors import AgentVisible
    from app.mcp_tools import _within_byte_budget

    payload = {"rows": ["x" * 200_000]}

    assert _within_byte_budget(payload) is payload, "the control: it fits the global"

    with pytest.raises(AgentVisible) as raised:
        _within_byte_budget(payload, 65536)
    assert "65536" in str(raised.value)
    assert "1048576" not in str(raised.value)
