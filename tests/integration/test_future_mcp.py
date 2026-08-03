"""Agent capability surface, owned by Sessions 8 and 9.

`AGT-SQL-001` is the load-bearing one. The product's central claim is that an
agent has no path to arbitrary SQL under any authentication, and that claim is
only worth what this test proves.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=8, requirement="AGT-READ-001")
def test_mcp_read_equals_the_postgrest_result() -> None:
    unimplemented(8, "the same identity gets identical RLS-constrained rows both ways")


@pytest.mark.future(session=8, requirement="AGT-SQL-001")
def test_no_tool_accepts_sql_or_a_raw_query_string() -> None:
    unimplemented(8, "every input is structured; no SQL, fragment, or query string")


@pytest.mark.future(session=8, requirement="AGT-SCOPE-001")
def test_tool_discovery_respects_scopes() -> None:
    unimplemented(8, "an agent cannot see a tool its scopes do not permit")


@pytest.mark.future(session=8, requirement="AGT-DRIFT-001")
def test_new_api_operation_does_not_become_agent_visible() -> None:
    unimplemented(8, "adding an endpoint changes nothing without a capabilities.yaml edit")


@pytest.mark.future(session=8, requirement="AGT-BUDGET-001")
def test_response_row_and_byte_budgets_are_enforced() -> None:
    unimplemented(8, "server-side limits hold regardless of client input")


@pytest.mark.future(session=9, requirement="AGT-WRITE-001")
def test_read_only_agent_cannot_discover_or_invoke_writes() -> None:
    unimplemented(9, "writes are neither listed nor callable for a read-only agent")


@pytest.mark.future(session=9, requirement="AGT-AUDIT-001")
def test_all_tool_outcomes_are_audited_with_redaction() -> None:
    unimplemented(9, "allowed, denied, and failed attempts are recorded without secrets")


@pytest.mark.future(session=9, requirement="AGT-AUDITFAIL-001")
def test_write_fails_closed_when_the_audit_record_cannot_be_created() -> None:
    unimplemented(9, "an unauditable write does not happen")
