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
