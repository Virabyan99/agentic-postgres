"""Deployment, isolation, operations, and developer experience.

These are marked ``deployment`` rather than ``contract`` even though they live
under tests/contract/, because the Session 1 gate runs ``-m "contract and not
future"`` and these are not Session 1 work. The marker, not the directory,
decides what runs.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.p0, pytest.mark.deployment]


def unimplemented(session: int, what: str) -> None:
    pytest.fail(f"Replace this placeholder with the Session {session} implementation: {what}")


@pytest.mark.future(session=11, requirement="DEP-001")
def test_fresh_project_deploys_on_an_empty_host() -> None:
    unimplemented(11, "a clean host reaches a working deployment from the README alone")


@pytest.mark.future(session=11, requirement="DEP-002")
def test_redeploy_is_idempotent_and_preserves_data() -> None:
    unimplemented(11, "re-running deploy converges without destroying rows")


@pytest.mark.future(session=11, requirement="DEP-PRE-001")
def test_failed_prerequisite_stops_before_changing_the_deployment() -> None:
    unimplemented(11, "a missing prerequisite lists everything absent and changes nothing")


@pytest.mark.future(session=12, requirement="DEP-ISO-001")
def test_two_projects_share_no_state_or_authority() -> None:
    unimplemented(12, "the full runtime isolation matrix across two live deployments")


@pytest.mark.future(session=12, requirement="DEP-REMOVE-001")
def test_removing_the_second_project_does_not_affect_the_first() -> None:
    unimplemented(12, "destructive removal is scoped to one project")


@pytest.mark.future(session=11, requirement="OPS-001")
def test_doctor_reports_required_checks_without_secrets() -> None:
    unimplemented(11, "container, TLS, database, backup, and disk checks, all redacted")


@pytest.mark.future(session=11, requirement="OPS-LOG-001")
def test_request_id_propagates_across_the_stack() -> None:
    unimplemented(11, "one request ID appears in Traefik, MCP, API, and audit records")


@pytest.mark.future(session=12, requirement="DX-001")
def test_new_team_member_completes_the_documented_path() -> None:
    unimplemented(12, "a developer who did not build this reaches a working deployment")
