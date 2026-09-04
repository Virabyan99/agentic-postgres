"""The evaluation harness (ADR 0184, `EVAL-HARNESS-001`): every derived and
written case, run against the agent plane's own request builders.

**The load-bearing test is `test_the_derived_adversarial_cases_reach_their
_fields`**, and it is the session plan's stop condition made into an assertion.
A harness whose every adversarial case is refused by the same first check
measures one guard and not the contract. The scope check runs first in this
runtime, so a case that withholds a scope must be refused by it and a case that
holds every scope must be refused by something else -- otherwise the case never
reached the field it targets. That rule is structural; it names no reason per
case, which is what D868 forbids.

A case carries an expectation and the evaluation records the outcome -- the
caller-facing token, the audit-side reason, the built request's target. What is
asserted per case is the expectation; the reasons are asserted only in
aggregate.

Nothing here reaches a database or a network. `execute` and `execute_write` are
replaced by fakes that record the request and return whatever the case's
`upstream` says, which is exactly what `test_mcp_tools.py` does one case at a
time and this module does for all of them.
"""

from __future__ import annotations

import copy
import inspect
import json
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, capability_compiler
from agentic_postgres import evaluation_harness as harness
from agentic_postgres.evaluation_harness import Case, HarnessError
from app import mcp_errors, mcp_tools
from app.mcp_errors import AgentVisible
from app.mcp_lock import WRITE_TOOLS, CapabilityLock, load_lock
from app.mcp_tools import ToolRefusal
from app.mcp_upstream import AgentContext

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
REPORT = REPO_ROOT / "docs" / "evaluation-report.md"

BASE = "http://postgrest:3000"
OWNER = "aaaaaaaa-0000-4000-8000-000000000001"
REQUEST_ID = "7f3a1c20-0000-4000-8000-0000000000bb"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text("utf-8"))


@pytest.fixture(scope="module")
def derived(contract: dict[str, Any]) -> tuple[Case, ...]:
    return harness.derive_cases(contract)


@pytest.fixture(scope="module")
def written(contract: dict[str, Any]) -> tuple[Case, ...]:
    return harness.load_written_cases(contract)


@pytest.fixture(scope="module")
def cases(derived: tuple[Case, ...], written: tuple[Case, ...]) -> dict[str, Case]:
    return {case.id: case for case in (*derived, *written)}


@pytest.fixture(scope="module")
def lock(contract: dict[str, Any], tmp_path_factory: pytest.TempPathFactory) -> CapabilityLock:
    """The approved contract as the runtime would load it: through the real
    compiler and the real loader, so a case runs against the lock the plane
    obeys rather than against a hand-built fixture (question 6)."""
    document = capability_compiler.compile_lock(
        canonical=contract,
        project_key="eval-dev",
        upstream="https://eval-dev.test/api/rest",
        sources={
            "capabilities_sha256": "a" * 64,
            "api_surface_sha256": "b" * 64,
            "canonical_openapi_sha256": "c" * 64,
        },
    )
    path = tmp_path_factory.mktemp("lock") / "lock.json"
    path.write_bytes(capability_compiler.canonical_bytes(document))
    return load_lock(path)


@dataclass(frozen=True)
class Outcome:
    status: str
    token: str | None
    reason: str | None
    target: str | None
    result: Any
    captured: dict[str, Any]


def evaluate(case: Case, lock: CapabilityLock, monkeypatch: pytest.MonkeyPatch) -> Outcome:
    """Run one case: the caller holds `case.scopes`, the upstream answers as
    `case.upstream` says, and the outcome is recorded rather than judged."""
    monkeypatch.setattr(
        mcp_tools,
        "current_agent_context",
        lambda: AgentContext(
            agent_id="eval-agent",
            role_name="apg_eval_dev_agent_writer",
            scopes=tuple(case.scopes),
            authz_version=1,
            owner_id=OWNER,
        ),
    )
    captured: dict[str, Any] = {}

    def rows() -> list[dict[str, Any]]:
        count = int(case.upstream.get("rows", 1))
        size = case.upstream.get("bytes")
        row = {"id": "row"} if size is None else {"blob": "x" * int(size)}
        return [dict(row) for _ in range(count)]

    def execute(base_url: str, token: str, request: Any, *, request_id: str) -> Any:
        captured["request"] = request
        return rows()

    def execute_write(base_url: str, token: str, request: Any, **kwargs: Any) -> Any:
        captured["request"] = request
        captured.update(kwargs)
        return rows()

    monkeypatch.setattr(mcp_tools, "execute", execute)
    monkeypatch.setattr(mcp_tools, "execute_write", execute_write)

    call = dict(case.call)
    tool = call.pop("tool")
    try:
        if tool == "list_resources":
            result = mcp_tools.list_resources(lock)
        elif tool == "describe_resource":
            result = mcp_tools.describe_resource(
                lock, tool=call["read_tool"], resource=call["resource"]
            )
        elif tool == "query_resource":
            result = mcp_tools.query_resource(
                lock,
                base_url=BASE,
                token="t",  # noqa: S106 -- a fixture token
                request_id=REQUEST_ID,
                resource=call["resource"],
                columns=call.get("columns"),
                filters=call.get("filters"),
                order_by=call.get("order_by"),
                limit=call.get("limit"),
            )
        elif tool == "run_report":
            result = mcp_tools.run_report(
                lock,
                base_url=BASE,
                token="t",  # noqa: S106
                request_id=REQUEST_ID,
            )
        elif tool in WRITE_TOOLS:
            result = mcp_tools.invoke_write(
                lock,
                base_url=BASE,
                token="t",  # noqa: S106
                request_id=REQUEST_ID,
                tool=tool,
                arguments=call["arguments"],
                idempotency_key=call["idempotency_key"],
                dry_run=call["dry_run"],
            )
        else:
            pytest.fail(f"{case.id} names a tool the evaluation cannot run: {tool!r}")
    except AgentVisible as refusal:
        return Outcome("refused", refusal.token, refusal.reason, _target(captured), None, captured)
    except ToolRefusal as refusal:
        return Outcome("refused", None, refusal.reason, _target(captured), None, captured)
    return Outcome("permitted", None, None, _target(captured), result, captured)


def _target(captured: dict[str, Any]) -> str | None:
    request = captured.get("request")
    return None if request is None else request.target


def _bound_holds(case: Case, lock: CapabilityLock, outcome: Outcome) -> str | None:
    """For a `bounded` case: the reason the bound did NOT hold, or None."""
    if case.field == "max_rows" and case.tool == "query_resource":
        ceiling = lock.resource("query_resource", case.call["resource"]).max_rows
        if outcome.target is None or f"limit={ceiling}" not in outcome.target:
            return f"the built request is {outcome.target!r}; the ceiling is {ceiling}"
        if case.call["limit"] <= ceiling:
            return "the case did not ask for more than the ceiling, so it bounded nothing"
        return None
    if case.field == "required_scopes" and case.tool == "list_resources":
        held = set(case.scopes)
        expected = sorted(
            resource.name
            for tool in lock.tools
            for resource in tool.resources
            if set(resource.required_scopes) <= held
        )
        listed = sorted(entry["resource"] for entry in outcome.result["resources"])
        if listed != expected:
            return f"listed {listed}, and the caller's scopes admit exactly {expected}"
        everything = sorted(r.name for t in lock.tools for r in t.resources)
        if listed == everything:
            return "the listing was not filtered at all, so the case bounded nothing"
        return None
    return f"no bound check is defined for {case.field} on {case.tool}"


# ---------------------------------------------------------------------------
# Every case, one node each
# ---------------------------------------------------------------------------


def _case_ids() -> list[str]:
    document = json.loads(CONTRACT.read_text("utf-8"))
    return [
        case.id for case in (*harness.derive_cases(document), *harness.load_written_cases(document))
    ]


@pytest.mark.parametrize("case_id", _case_ids())
def test_each_case_meets_its_expectation(
    case_id: str, cases: dict[str, Case], lock: CapabilityLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expectation is the contract's; the reason is observed and recorded."""
    case = cases[case_id]
    outcome = evaluate(case, lock, monkeypatch)
    if case.expects == "permitted":
        assert outcome.status == "permitted", (
            f"{case.id}: the contract permits this and the runtime refused it "
            f"({outcome.token}, {outcome.reason})"
        )
    elif case.expects == "refused":
        assert outcome.status == "refused", f"{case.id}: the contract does not permit this"
        assert outcome.reason in mcp_errors.DENIAL_REASONS, outcome.reason
    else:
        assert outcome.status == "permitted", f"{case.id}: a bounded call was refused"
        failure = _bound_holds(case, lock, outcome)
        assert failure is None, f"{case.id}: {failure}"


# ---------------------------------------------------------------------------
# The stop condition (plan §9): not all refused by the same first check
# ---------------------------------------------------------------------------


def test_the_derived_adversarial_cases_reach_their_fields(
    derived: tuple[Case, ...], lock: CapabilityLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A case holding every scope it needs and refused by the scope check never
    reached the field it targets. Asserted structurally, never per reason."""
    reasons: dict[str, str] = {}
    for case in derived:
        if case.kind != "adversarial" or case.expects != "refused":
            continue
        outcome = evaluate(case, lock, monkeypatch)
        assert outcome.status == "refused", case.id
        assert outcome.reason is not None
        reasons[case.id] = outcome.reason

    scope_cases = {i: r for i, r in reasons.items() if i.endswith(":required_scopes")}
    other_cases = {i: r for i, r in reasons.items() if i not in scope_cases}
    assert scope_cases and other_cases

    wrong_scope = {i: r for i, r in scope_cases.items() if r != mcp_errors.SCOPE_NOT_HELD_REASON}
    assert not wrong_scope, (
        f"a scope case was refused by something other than the scope check: {wrong_scope}"
    )

    stopped_early = {i: r for i, r in other_cases.items() if r == mcp_errors.SCOPE_NOT_HELD_REASON}
    assert not stopped_early, (
        f"these hold every scope they need and were refused by the scope check, so they "
        f"never reached the field they target: {stopped_early}"
    )

    distinct = sorted(set(other_cases.values()))
    assert len(distinct) >= 3, (
        f"the non-scope refusals come from only {distinct}; the harness is measuring "
        "one guard rather than the contract (plan §9's stop condition)"
    )
    # The response-side cases are refused by the way OUT, and that is a
    # different boundary from the request-side ones -- asserted so a harness
    # whose fake upstream was never consulted could not pass on request refusals.
    response = {i: r for i, r in other_cases.items() if i.endswith(".response") or "bytes" in i}
    assert response and all(r != mcp_errors.NOT_IN_ALLOWLIST for r in response.values()), response


# ---------------------------------------------------------------------------
# Coverage, and the enforcement that fails the gate and CI
# ---------------------------------------------------------------------------


def test_every_capability_has_cases_of_both_kinds_and_origins(
    contract: dict[str, Any], derived: tuple[Case, ...], written: tuple[Case, ...]
) -> None:
    """Derived and written are counted apart, and a capability short of either
    is refused -- the control removes one capability's written cases."""
    table = harness.coverage(contract, derived, written)
    assert set(table) == set(harness.capabilities_of(contract))
    for name, row in table.items():
        for column in (
            "derived_positive",
            "derived_adversarial",
            "written_positive",
            "written_adversarial",
        ):
            assert row[column] >= 1, (name, column, row)

    without = tuple(case for case in written if case.capability != "list_resources")
    with pytest.raises(HarnessError, match="list_resources"):
        harness.coverage(contract, derived, without)

    # And the renderer runs the same check before writing a line, so the gate's
    # `--check` and CI refuse the same state (read, because a subprocess cannot
    # be handed a case file the module-level path does not name).
    assert "coverage(" in inspect.getsource(harness.render_report)


def test_a_written_case_bound_to_a_stale_version_is_refused(
    contract: dict[str, Any], tmp_path: Path
) -> None:
    """A capability that changed must have its cases re-read. The control is
    the shipped file, which loads."""
    document = yaml.safe_load(harness.WRITTEN_CASES_PATH.read_text("utf-8"))
    document[0]["capability_version"] = "9.9.9"
    stale = tmp_path / "cases.yaml"
    stale.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(HarnessError, match=r"written against '9\.9\.9'"):
        harness.load_written_cases(contract, stale)
    assert harness.load_written_cases(contract), "the control: the shipped file loads"

    # A version the contract declares is exactly the manifest's, so the binding
    # is to the reviewed manifest's field and not to a number this file made up.
    versions = {e["version"] for tool in contract["tools"] for e in tool["capabilities"]}
    assert {c.capability_version for c in harness.load_written_cases(contract)} <= versions


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("capability", lambda e: e.update({"capability": "delete_everything"})),
        ("call.tool", lambda e: e["call"].update({"tool": "create_note"})),
        ("expects", lambda e: e.update({"expects": "tolerated"})),
        ("unknown key", lambda e: e.update({"reason": "not_in_allowlist"})),
    ],
)
def test_a_malformed_written_case_is_refused(
    contract: dict[str, Any], tmp_path: Path, field: str, mutate: Any
) -> None:
    """Including one carrying a `reason`: a written case may not assert the
    denial reason either (D868), so the key is not part of the shape."""
    document = yaml.safe_load(harness.WRITTEN_CASES_PATH.read_text("utf-8"))
    mutate(document[0])
    path = tmp_path / "cases.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(HarnessError):
        harness.load_written_cases(contract, path)


def test_the_derivation_follows_the_contract(contract: dict[str, Any]) -> None:
    """The control against a hand-kept list: move the contract, the cases move.

    Deterministic on the same contract; different on a contract whose ceiling,
    orderings or declarations differ. Each mutation is checked to change the
    one case that targets the field it moved, and nothing about the others.
    """
    baseline = {c.id: c for c in harness.derive_cases(contract)}
    assert harness.derive_cases(contract) == tuple(baseline.values())

    moved = copy.deepcopy(contract)
    query = next(t for t in moved["tools"] if t["name"] == "query_resource")
    notes = next(r for r in query["resources"] if r["name"] == "notes")
    notes["max_rows"] = 7
    notes["order_by"] = notes["order_by"][:1]
    changed = {c.id: c for c in harness.derive_cases(moved)}
    assert changed["derived:query_notes:max_rows"].call["limit"] == 8
    assert changed["derived:query_notes:max_rows.response"].upstream["rows"] == 8
    assert changed["derived:query_notes:order_by"].call["order_by"] == 1
    untouched = [i for i in baseline if i in changed and not i.startswith("derived:query_notes:")]
    assert all(baseline[i] == changed[i] for i in untouched)

    # A write that stops supporting a rehearsal: the dry-run case flips from a
    # positive to an adversarial one, because asking is then not permitted.
    create = next(t for t in moved["tools"] if t["name"] == "create_note")
    create["supports_dry_run"] = False
    flipped = {c.id: c for c in harness.derive_cases(moved)}
    assert flipped["derived:create_note:supports_dry_run"].kind == "adversarial"
    assert flipped["derived:create_note:supports_dry_run"].expects == "refused"
    assert baseline["derived:create_note:supports_dry_run"].kind == "positive"

    # A write that requires approval loses its positive and gains the refusal.
    create["requires_approval"] = True
    gated = {c.id: c for c in harness.derive_cases(moved)}
    assert "derived:create_note:positive" not in gated
    assert gated["derived:create_note:requires_approval"].expects == "refused"


def test_a_version_one_contract_derives_only_the_fields_it_carries(
    contract: dict[str, Any],
) -> None:
    """A v1 contract declares no budgets and no write declarations, so the
    cases that target them are not derived -- absent, not expecting a refusal
    the contract never promised (D600)."""
    v1 = copy.deepcopy(contract)
    v1["schema_version"] = 1
    for tool in v1["tools"]:
        for key in (
            "capabilities",
            "risk",
            "max_response_bytes",
            "max_concurrent_calls",
            "supports_dry_run",
            "requires_approval",
        ):
            tool.pop(key, None)
    ids = {c.id for c in harness.derive_cases(v1)}
    assert not any(i.endswith(":max_response_bytes") for i in ids)
    assert not any(i.endswith(":supports_dry_run") for i in ids)
    assert "derived:query_notes:max_rows" in ids, "the row ceiling exists at every version"
    assert all(c.capability_version is None for c in harness.derive_cases(v1))


# ---------------------------------------------------------------------------
# The report, the digest and the roster copies
# ---------------------------------------------------------------------------


def test_the_report_is_current_and_carries_the_contracts_digest(
    contract: dict[str, Any],
) -> None:
    """The digest in the report is the lock's `canonical_sha256` and the
    deployed document's `capability_contract_sha256`, byte for byte."""
    check = subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "render-evaluation-report.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert check.returncode == 0, check.stderr

    digest = harness.contract_digest(contract)
    assert digest == sha256(capability_compiler.canonical_bytes(contract)).hexdigest()
    lock = capability_compiler.compile_lock(
        canonical=contract,
        project_key="eval-dev",
        upstream="https://eval-dev.test/api/rest",
        sources={
            "capabilities_sha256": "a" * 64,
            "api_surface_sha256": "b" * 64,
            "canonical_openapi_sha256": "c" * 64,
        },
    )
    assert lock["canonical_sha256"] == digest
    assert digest in REPORT.read_text("utf-8")


def test_the_report_carries_no_outcome(contract: dict[str, Any]) -> None:
    """What was asked, never what was answered: no denial reason and no
    observed token appears in the generated block."""
    generated = REPORT.read_text("utf-8").split("<!-- BEGIN GENERATED: evaluation-report -->")[1]
    for reason in mcp_errors.DENIAL_REASONS:
        assert f"`{reason}`" not in generated and f" {reason} " not in generated, reason
    assert "PASSED" not in generated and "FAILED" not in generated


def test_the_reserved_parameters_and_the_operators_are_the_runtimes() -> None:
    """The third copy of the roster, with the same test between them (D486);
    and the operator vocabulary the harness reads from the schema is the one
    the runtime can spell, so a derived operator case names a real operator."""
    from app.mcp_query import OPERATORS

    assert harness.RESERVED_WRITE_PARAMETERS == mcp_tools.RESERVED_WRITE_PARAMETERS
    assert set(harness.filter_operators()) == set(OPERATORS)


def test_a_derived_rehearsal_reaches_the_transport_with_both_reserved_parameters(
    cases: dict[str, Case], lock: CapabilityLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive dry-run case is not satisfied by a runtime that ignored the
    flag: the transport must receive `dry_run=True` and the derived key."""
    outcome = evaluate(cases["derived:create_note:supports_dry_run"], lock, monkeypatch)
    assert outcome.status == "permitted"
    assert outcome.captured["dry_run"] is True
    assert outcome.captured["idempotency_key"] == harness.DERIVED_IDEMPOTENCY_KEY
    assert outcome.result["dry_run"] is True and outcome.result["row_count"] == 0


def test_the_hostile_value_is_percent_encoded_in_the_built_target(
    cases: dict[str, Case], lock: CapabilityLock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The written injection case is permitted BECAUSE the string is a value,
    and the target the evaluation recorded shows it encoded, never interpolated."""
    outcome = evaluate(
        cases["written:query_notes:a-hostile-value-stays-a-value"], lock, monkeypatch
    )
    assert outcome.status == "permitted"
    assert outcome.target is not None
    assert "'" not in outcome.target and " " not in outcome.target
    assert "%27" in outcome.target and "DROP" in outcome.target


def test_the_bound_check_can_tell_a_clamped_request_from_an_honoured_one(
    cases: dict[str, Case], lock: CapabilityLock
) -> None:
    """**The control of the control** (D509). A `bounded` case passes when
    `_bound_holds` returns None, so a checker that returned None for everything
    would pass every bounded case against a runtime that honoured the caller's
    limit -- and the mutation battery found exactly that arm surviving, because
    a checker defect has no witness in a suite where the runtime is correct.
    This is the witness: a fabricated outcome whose target carries the caller's
    limit rather than the ceiling must be reported, and one carrying the
    ceiling must not."""
    case = cases["derived:query_notes:max_rows"]
    ceiling = lock.resource("query_resource", "notes").max_rows
    honoured = Outcome("permitted", None, None, f"/notes?limit={ceiling + 1}", {}, {})
    clamped = Outcome("permitted", None, None, f"/notes?limit={ceiling}", {}, {})
    assert _bound_holds(case, lock, honoured) is not None, (
        "an honoured limit was reported as bounded"
    )
    assert _bound_holds(case, lock, clamped) is None

    listing = cases["derived:list_resources:required_scopes"]
    everything = {"resources": [{"resource": r.name} for t in lock.tools for r in t.resources]}
    unfiltered = Outcome("permitted", None, None, None, everything, {})
    assert _bound_holds(listing, lock, unfiltered) is not None, "an unfiltered listing passed"
    empty = Outcome("permitted", None, None, None, {"resources": []}, {})
    assert _bound_holds(listing, lock, empty) is None
