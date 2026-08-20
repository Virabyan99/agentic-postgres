"""Agent capability surface still owned by Session 9.

**Session 8's five placeholders are gone**, replaced in Run 6 by real tests:
`AGT-SQL-001`, `AGT-SCOPE-001`, `AGT-READ-001` and `AGT-BUDGET-001` live in
`tests/contract/test_mcp_tools.py`, and `AGT-DRIFT-001` has been in
`tests/contract/test_capability_compiler.py` since Run 3. The registry points at
those, which is what lets `CURRENT_SESSION` move to 8 in Run 7 without reddening
the gate (D414).

What remains here is Session 9's: the write plane and the durable audit record.
`AGT-SQL-001` used to be described as the load-bearing one in this file, and it
still is -- it has simply moved to a module that can prove it.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.integration]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=9, requirement="AGT-WRITE-001")
def test_read_only_agent_cannot_discover_or_invoke_writes() -> None:
    unimplemented(9, "writes are neither listed nor callable for a read-only agent")


@pytest.mark.future(session=9, requirement="AGT-AUDIT-001")
def test_all_tool_outcomes_are_audited_with_redaction() -> None:
    unimplemented(9, "allowed, denied, and failed attempts are recorded without secrets")


@pytest.mark.future(session=9, requirement="AGT-AUDITFAIL-001")
def test_write_fails_closed_when_the_audit_record_cannot_be_created() -> None:
    unimplemented(9, "an unauditable write does not happen")
