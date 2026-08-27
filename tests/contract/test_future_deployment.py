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


@pytest.mark.future(session=12, requirement="DEP-001")
def test_fresh_project_deploys_on_an_empty_host() -> None:
    unimplemented(12, "a clean host reaches a working deployment from the README alone")


@pytest.mark.future(session=12, requirement="DEP-ISO-001")
def test_two_projects_share_no_state_or_authority() -> None:
    unimplemented(12, "the full runtime isolation matrix across two live deployments")


@pytest.mark.future(session=12, requirement="DEP-REMOVE-001")
def test_removing_the_second_project_does_not_affect_the_first() -> None:
    unimplemented(12, "destructive removal is scoped to one project")


# ---------------------------------------------------------------------------
# Session 11 — activated in Run 9
#
#   DEP-002      -> tests/deployment/test_session11_operations.py
#   DEP-PRE-001  -> tests/contract/test_preflight.py
#                   tests/deployment/test_session11_operations.py
#   OPS-001      -> tests/contract/test_diagnosis.py
#                   tests/contract/test_doctor_redaction.py
#                   tests/deployment/test_session11_operations.py
#   OPS-LOG-001  -> tests/contract/test_request_id_stamping.py
#                   tests/deployment/test_session11_operations.py    (ingress)
#                   tests/deployment/test_session9_agent_writes.py   (both rows)
#
# Removed rather than kept beside their implementations: a placeholder next to a
# real test is a second, weaker claim about the same requirement, which is what
# `test_no_requirement_is_claimed_by_two_placeholders` exists to prevent.
#
# DEP-002 and DEP-PRE-001 each gained a node id beyond the obvious one (D70): a
# preserved row with no control is satisfied by a deploy that did nothing, and
# "changed nothing" is a different claim from "listed everything".
#
# **DEP-001 stays a placeholder, deliberately** (D669). Its offline half is
# proved and its live half -- a fresh project deploying on an empty host -- was
# not run: Run 8's rehearsal stopped after the host baseline and the edge plane,
# because leg 3 needed scratch provider state in order to exercise the commands
# the live host already runs on every deploy. Session 12 inherits it beside
# DX-001, which is a superset of it.
# ---------------------------------------------------------------------------


@pytest.mark.future(session=12, requirement="DX-001")
def test_new_team_member_completes_the_documented_path() -> None:
    unimplemented(12, "a developer who did not build this reaches a working deployment")


# ---------------------------------------------------------------------------
# Session 5 — activated in Run 8
#
#   DEP-ISO-005  -> tests/deployment/test_session5_api_isolation.py
#   DX-API-001   -> tests/deployment/test_session5_api_tooling.py
#
# DEP-ISO-005's cross-project clause gained a node ID of its own, which is what
# the comment that used to sit here said Run 8 would have to do. "The routes
# differ" and "one project's token is refused by the other" are different
# claims, and a requirement whose description is broader than its node IDs is a
# claim the evidence file reports as passed (D70).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session 4 — activated in Run 8
#
# The four placeholders that were here are gone rather than kept beside their
# implementations: a placeholder next to a real test is a second, weaker claim
# about the same requirement, which is what
# test_no_requirement_is_claimed_by_two_placeholders exists to prevent.
#
#   DBX-PORT-001, DEP-ISO-004  -> tests/deployment/test_session4_transports.py
#                                 tests/deployment/test_session4_isolation.py
#   DX-DB-001, DX-DB-002       -> tests/external/test_session4_public_transports.py
#
# DEP-ISO-004's credential clause gained a node ID of its own, which is what the
# comment that used to sit here said Run 8 would have to do (D70).
# ---------------------------------------------------------------------------
