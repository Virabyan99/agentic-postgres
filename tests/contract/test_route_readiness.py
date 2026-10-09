"""`tests/deployment/route_readiness.py`, offline (D2294, D2143).

The rule two live proofs share -- DEP-REMOVE-001's survivor and REC-NODE-002's
replacement -- is that a route is excused from `ready` ONLY when the same
deployed document declares its facility `enabled: false`. The live proofs run
on a host; this holds the rule on every commit, with the controls the repair
must not reach: a served route that is down is still reported, and a document
that does not say excuses nothing.

The documents are built in the shape the deployed ones have (measured on OVH's
three on 2026-10-09: alpha and beta `control.enabled: false` with
`routes.control` `unavailable`; control-prod `storage.enabled: false` with
`routes.storage` `unavailable`).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from tests.deployment.route_readiness import FACILITY_ROUTES, not_served, unready_routes

pytestmark = [pytest.mark.contract, pytest.mark.p0]

READY = {"status": "ready", "url": "https://x.example/route"}
NOT_PUBLISHED = {"status": "unavailable", "url": None}
ROUTES = ("app", "app_docs", "control", "docs", "health", "mcp", "metrics", "rest", "storage")


def _document(*, control: bool, storage: bool) -> dict[str, Any]:
    routes = {name: dict(READY) for name in ROUTES}
    if not control:
        routes["control"] = dict(NOT_PUBLISHED)
    if not storage:
        routes["storage"] = dict(NOT_PUBLISHED)
    return {"control": {"enabled": control}, "storage": {"enabled": storage}, "routes": routes}


def test_a_route_whose_facility_the_document_turns_off_is_excused() -> None:
    alpha = _document(control=False, storage=True)
    control_prod = _document(control=True, storage=False)
    assert not_served(alpha) == {"control"}
    assert not_served(control_prod) == {"storage"}
    assert unready_routes(alpha) == []
    assert unready_routes(control_prod) == []


def test_a_served_route_that_is_down_is_still_reported() -> None:
    """The controls D2143 and D2294 were verified with on the real documents."""
    alpha = _document(control=False, storage=True)
    alpha["routes"]["storage"] = dict(NOT_PUBLISHED)
    assert unready_routes(alpha) == ["storage"]

    control_prod = _document(control=True, storage=False)
    control_prod["routes"]["control"] = {"status": "unobserved", "url": None}
    assert unready_routes(control_prod) == ["control"]

    # A route outside the facility set is never excused, whatever the flags say.
    for name in ("rest", "app", "health"):
        down = _document(control=False, storage=False)
        down["routes"][name] = dict(NOT_PUBLISHED)
        assert unready_routes(down) == [name]


def test_a_document_that_does_not_say_excuses_nothing() -> None:
    silent = _document(control=False, storage=True)
    del silent["control"]
    assert unready_routes(silent) == ["control"]
    unknown = copy.deepcopy(silent)
    unknown["control"] = {"enabled": None}
    assert unready_routes(unknown) == ["control"]
    assert FACILITY_ROUTES == ("control", "storage"), (
        "a new facility route is excused only once the document carries its flag"
    )
