"""A deployed document may wait for a fact, but never invent one.

The first real deployment of Project A recorded `tls: unavailable` and
`health: unavailable` while the route was answering `200` from two networks.
The observations ran the instant `compose up --wait` returned, before Traefik's
Docker provider had wired the router. Nothing was wrong with the deployment; the
evidence was wrong about it.

These tests pin the two halves of the fix that matter: it must keep observing
until the fact settles, and it must still report an unsettled fact honestly
rather than defaulting to the value the deploy hoped for.
"""

from __future__ import annotations

import pytest

from agentic_postgres import observation

pytestmark = [pytest.mark.contract, pytest.mark.p0]


class Clock:
    """A monotonic clock that only advances when something sleeps.

    The loop under test is the real one. Only the passage of time is simulated,
    so a 90-second timeout costs no wall time and the test cannot pass by
    exercising a stand-in for the code that ships.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def test_a_fact_that_is_already_true_costs_no_waiting() -> None:
    clock = Clock()
    calls = []

    result = observation.await_observation(
        lambda: calls.append(1) or "ready",
        lambda value: value == "ready",
        sleep=clock.sleep,
        now=clock.monotonic,
    )

    assert result == "ready"
    assert len(calls) == 1
    assert clock.slept == []


def test_it_keeps_observing_until_the_fact_settles() -> None:
    """The defect: Traefik had not wired the router yet at the first look."""
    clock = Clock()
    answers = iter(["unavailable", "unavailable", "ready"])

    result = observation.await_observation(
        lambda: next(answers),
        lambda value: value == "ready",
        interval=3.0,
        sleep=clock.sleep,
        now=clock.monotonic,
    )

    assert result == "ready"
    assert clock.slept == [3.0, 3.0]


def test_an_unsettled_fact_is_reported_not_defaulted() -> None:
    """Waiting is not assuming. A route that never comes up must say so."""
    clock = Clock()

    result = observation.await_observation(
        lambda: "unavailable",
        lambda value: value == "ready",
        timeout=10.0,
        interval=3.0,
        sleep=clock.sleep,
        now=clock.monotonic,
    )

    assert result == "unavailable"
    assert clock.monotonic() >= 10.0


def test_the_last_observation_is_not_discarded_for_arriving_late() -> None:
    """The deadline is checked after observing, not before.

    Checking first would throw away a fact that became true on the very poll
    that crossed the deadline -- reporting a working route as unavailable, which
    is the defect this module exists to remove.
    """
    clock = Clock()
    answers = iter(["unavailable", "ready"])

    result = observation.await_observation(
        lambda: next(answers),
        lambda value: value == "ready",
        timeout=3.0,
        interval=3.0,
        sleep=clock.sleep,
        now=clock.monotonic,
    )

    assert result == "ready"


def test_observe_is_called_at_least_once_even_with_no_timeout() -> None:
    clock = Clock()
    calls = []

    result = observation.await_observation(
        lambda: calls.append(1) or "unavailable",
        lambda value: value == "ready",
        timeout=0.0,
        sleep=clock.sleep,
        now=clock.monotonic,
    )

    assert result == "unavailable"
    assert len(calls) == 1
    assert clock.slept == []


@pytest.mark.parametrize(
    ("timeout", "interval"),
    [(-1.0, 3.0), (10.0, 0.0), (10.0, -1.0)],
)
def test_nonsense_bounds_are_refused(timeout: float, interval: float) -> None:
    """A zero interval spins; a negative timeout is a caller error, not a
    request to observe forever."""
    with pytest.raises(ValueError):
        observation.await_observation(
            lambda: "unavailable",
            lambda value: value == "ready",
            timeout=timeout,
            interval=interval,
        )


def test_the_deploy_waits_for_both_observations(code_only) -> None:
    """Guard against the wiring being dropped while the module survives.

    Asserted against the deploy's source because the alternative is a live
    deployment, which this suite must not perform.
    """
    from agentic_postgres import REPO_ROOT

    body = code_only((REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8"))
    assert "await_observation" in body, "the deploy observes once and records the race"
    assert body.count("await_observation") >= 2, "both tls and health must wait"


# ---------------------------------------------------------------------------
# The served document waits like its neighbours, and says which failure (D387)
# ---------------------------------------------------------------------------


def _deploy_module():
    """`bin/deploy-project.py`, loaded as a module, for `ServedDocument` alone."""
    import importlib.util

    from agentic_postgres import REPO_ROOT

    specification = importlib.util.spec_from_file_location(
        "apg_deploy_served_document", REPO_ROOT / "bin" / "deploy-project.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_only_an_unreachable_route_is_worth_waiting_for() -> None:
    """D387, and the half that keeps the window from being spent on nothing.

    Session 7's row named the consequence precisely: *a lost race makes the
    deployed document understate a working deployment -- and a claim computed
    from it would be wrong in the safe-looking direction.* The repair is the
    two-stage convergence every neighbouring observation in step 7 already has.

    But the three failures are not the same kind. A route that has not been
    wired yet converges; a documentation token that cannot be minted does not,
    and retrying it would spend ninety seconds on a deterministic failure and
    print the same line thirty times. So `settled` is false for exactly one of
    them, which is what `await_observation` waits on.
    """
    module = _deploy_module()

    served = module.ServedDocument("abc123", "served", "")
    unreachable = module.ServedDocument(None, "unreachable", "connection refused")
    no_token = module.ServedDocument(None, "no_token", "signing key absent")

    assert served.settled, "a successful reading would be retried until the deadline"
    assert not unreachable.settled, (
        "the one state that can change is treated as final, which is D387 unrepaired"
    )
    assert no_token.settled, (
        "a deterministic failure is retried, which spends the observation window "
        "and prints the same line on every poll"
    )

    # The two failures are distinguishable, which is the other half of the row:
    # a service that cannot serve its document and an edge that had not finished
    # attaching send an operator to different places.
    assert unreachable.outcome != no_token.outcome
    assert unreachable.detail and no_token.detail


def test_the_served_document_reading_is_one_of_the_deploys_waits(code_only) -> None:
    """The wiring, guarded against being dropped while the type survives.

    Asserted against the deploy's source for the reason the test above this
    file's own neighbour gives: the alternative is a live deployment, which this
    suite must not perform.
    """
    from agentic_postgres import REPO_ROOT

    body = code_only((REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8"))
    assert "observe_served_document" in body
    index = body.index("observe_served_document(")
    window = body[max(0, index - 400) : index]
    assert "await_observation" in window, (
        "the served-document reading is called outside an observation window, so a "
        "router that had not been wired yet still records api.status unavailable "
        "for a route that answers seconds later (D387)"
    )
    assert body.count("await_observation") >= 3, "tls, health and the served document must all wait"
