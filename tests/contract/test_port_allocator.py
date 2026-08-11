"""The allocation logic, and the publication it produces (Session 4 Run 4).

`test_port_allocations.py` covers the schema and ends by asserting that the
schema *accepts* a duplicate port and a repeated instance UUID, because
`uniqueItems` compares whole objects and cannot express either. This module is
the other side of that boundary: the two invariants that therefore have to live
in code, and the states the allocator must refuse.

The property under all of it is that **an allocation does not move**. A port
that changes silently breaks every developer's saved tunnel and every documented
command, and produces no error anywhere — the port is simply somebody else's
now, or nobody's. So most of what follows is about refusing to move one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import yaml

from agentic_postgres import port_allocations, runtime_override
from agentic_postgres.port_allocations import AllocationError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ALPHA = "0f9d2c31-5b7e-4a1f-9c33-8de1b4f60a72"
BETA = "b55f9932-6c35-453e-9f7e-887b2cb6db88"
RANGE = (15432, 15531)
MOMENT = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)


def registry(*allocations: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "allocations": list(allocations)}


def allocation(**overrides: Any) -> dict[str, Any]:
    base = {
        "instance_uuid": ALPHA,
        "project_key": "alpha-dev",
        "pooled_port": 15432,
        "direct_port": 15433,
        "state": "active",
        "reserved_at": "2026-08-08T12:00:00Z",
        "activated_at": "2026-08-08T12:00:05Z",
        "released_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# The two invariants JSON Schema cannot state
# ---------------------------------------------------------------------------


def test_two_live_allocations_may_not_share_a_port() -> None:
    """The worst thing this file can say, and the schema admits it.

    Two projects cannot both be reachable on one port; which one wins is decided
    by whichever container started second, which is not a property anybody
    designed.
    """
    with pytest.raises(AllocationError, match="claimed by both"):
        port_allocations.validate(
            registry(
                allocation(),
                allocation(instance_uuid=BETA, project_key="beta-dev", direct_port=15434),
            )
        )


def test_a_released_allocation_does_not_hold_its_ports() -> None:
    """The same pair is reusable once released, which is the point of releasing."""
    port_allocations.validate(
        registry(
            allocation(state="released", released_at="2026-08-09T09:00:00Z"),
            allocation(instance_uuid=BETA, project_key="beta-dev"),
        )
    )


def test_one_identity_may_not_appear_twice() -> None:
    with pytest.raises(AllocationError, match="appears in allocations"):
        port_allocations.validate(
            registry(allocation(), allocation(pooled_port=15440, direct_port=15441))
        )


def test_one_port_may_not_serve_both_transports() -> None:
    with pytest.raises(AllocationError, match="one port for both transports"):
        port_allocations.validate(registry(allocation(direct_port=15432)))


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def test_a_first_allocation_takes_the_lowest_free_pair() -> None:
    updated, made = port_allocations.allocate(
        registry(),
        instance_uuid=ALPHA,
        project_key="alpha-dev",
        port_range=RANGE,
        moment=MOMENT,
    )
    assert (made["pooled_port"], made["direct_port"]) == (15432, 15433)
    assert made["state"] == "reserved"
    assert made["activated_at"] is None
    assert len(updated["allocations"]) == 1


def test_a_second_project_does_not_take_the_first_ones_ports() -> None:
    first, _ = port_allocations.allocate(
        registry(), instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    _, second = port_allocations.allocate(
        first, instance_uuid=BETA, project_key="beta-dev", port_range=RANGE, moment=MOMENT
    )
    assert (second["pooled_port"], second["direct_port"]) == (15434, 15435)


def test_redeploy_returns_the_same_two_numbers() -> None:
    """Idempotence is the requirement, not a convenience.

    Those numbers are in somebody's saved tunnel and in the operator guide. A
    redeploy that reallocated would break both and report success.
    """
    first, made = port_allocations.allocate(
        registry(), instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    again, same = port_allocations.allocate(
        first, instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    assert same == made
    assert again == first


def test_reallocation_does_not_promote_a_reservation() -> None:
    """A crashed deploy must stay provably unadopted.

    If `allocate` promoted, a reservation nothing ever served would look exactly
    like a verified allocation, and the two-phase transition would buy nothing.
    """
    first, _ = port_allocations.allocate(
        registry(), instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    _, again = port_allocations.allocate(
        first, instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    assert again["state"] == "reserved"


def test_the_identity_is_matched_not_the_project_key() -> None:
    """A renamed project keeps its ports; a rebuilt one does not take them.

    This is the whole reason ADR 0042 keys on the volume's UUID, so it is
    asserted from both directions in one test.
    """
    existing = registry(allocation())

    _, renamed = port_allocations.allocate(
        existing,
        instance_uuid=ALPHA,
        project_key="alpha-renamed",
        port_range=RANGE,
        moment=MOMENT,
    )
    assert (renamed["pooled_port"], renamed["direct_port"]) == (15432, 15433)

    _, rebuilt = port_allocations.allocate(
        existing, instance_uuid=BETA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    assert (rebuilt["pooled_port"], rebuilt["direct_port"]) != (15432, 15433)


def test_ports_the_caller_could_not_bind_are_skipped() -> None:
    """The registry is not the only thing holding a port.

    Something unrelated to this system can be bound to one, and the registry has
    no idea. The caller probes and passes the answer in, under the same lock as
    the write.
    """
    usable = set(range(15434, 15532))
    _, made = port_allocations.allocate(
        registry(),
        instance_uuid=ALPHA,
        project_key="alpha-dev",
        port_range=RANGE,
        usable=usable,
        moment=MOMENT,
    )
    assert (made["pooled_port"], made["direct_port"]) == (15434, 15435)


def test_a_range_with_one_port_left_allocates_nothing() -> None:
    """Both ports or neither. A project with one is a state nothing converges."""
    with pytest.raises(AllocationError, match="allocated together"):
        port_allocations.allocate(
            registry(),
            instance_uuid=ALPHA,
            project_key="alpha-dev",
            port_range=RANGE,
            usable={15500},
            moment=MOMENT,
        )


def test_an_uppercase_uuid_is_refused() -> None:
    with pytest.raises(AllocationError, match="lowercase UUID"):
        port_allocations.allocate(
            registry(),
            instance_uuid=ALPHA.upper(),
            project_key="alpha-dev",
            port_range=RANGE,
            moment=MOMENT,
        )


# ---------------------------------------------------------------------------
# Release, and what a restored volume gets back
# ---------------------------------------------------------------------------


def test_a_restored_volume_gets_its_original_ports_back() -> None:
    """The property the fresh-UUID design would have lost, silently.

    Restore a backup, redeploy, and the developer's saved tunnel still works,
    because the identity came back with the data.
    """
    released = port_allocations.release(
        registry(allocation()), instance_uuid=ALPHA, project_key="alpha-dev", moment=MOMENT
    )
    _, restored = port_allocations.allocate(
        released, instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    assert (restored["pooled_port"], restored["direct_port"]) == (15432, 15433)
    assert restored["state"] == "reserved"


def test_a_restored_volume_whose_ports_were_taken_is_refused_rather_than_moved() -> None:
    """Refusing is better than moving, and this is the case that proves it.

    Silently reallocating onto a free pair would succeed, report success, and
    break every command an operator had written down.
    """
    released = port_allocations.release(
        registry(allocation()), instance_uuid=ALPHA, project_key="alpha-dev", moment=MOMENT
    )
    taken, _ = port_allocations.allocate(
        released, instance_uuid=BETA, project_key="beta-dev", port_range=RANGE, moment=MOMENT
    )
    with pytest.raises(AllocationError, match="no longer available"):
        port_allocations.allocate(
            taken, instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
        )


def test_release_refuses_a_misidentified_project() -> None:
    """The one operation that can hand a developer's port to someone else.

    So the caller has to name what they think they are releasing, and be told
    when they are wrong.
    """
    with pytest.raises(AllocationError, match="misidentified"):
        port_allocations.release(
            registry(allocation()), instance_uuid=ALPHA, project_key="beta-dev", moment=MOMENT
        )


def test_releasing_twice_is_not_an_error() -> None:
    once = port_allocations.release(
        registry(allocation()), instance_uuid=ALPHA, project_key="alpha-dev", moment=MOMENT
    )
    assert (
        port_allocations.release(once, instance_uuid=ALPHA, project_key="alpha-dev", moment=MOMENT)
        == once
    )


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def test_activation_records_when() -> None:
    reserved, _ = port_allocations.allocate(
        registry(), instance_uuid=ALPHA, project_key="alpha-dev", port_range=RANGE, moment=MOMENT
    )
    activated = port_allocations.activate(reserved, instance_uuid=ALPHA, moment=MOMENT)
    entry = port_allocations.find(activated, ALPHA)
    assert entry["state"] == "active"
    assert entry["activated_at"] == "2026-08-08T12:00:00Z"


def test_a_released_allocation_cannot_be_activated() -> None:
    released = port_allocations.release(
        registry(allocation()), instance_uuid=ALPHA, project_key="alpha-dev", moment=MOMENT
    )
    with pytest.raises(AllocationError, match="only a reservation becomes active"):
        port_allocations.activate(released, instance_uuid=ALPHA, moment=MOMENT)


def test_activating_an_unknown_identity_is_refused() -> None:
    with pytest.raises(AllocationError, match="no allocation"):
        port_allocations.activate(registry(), instance_uuid=ALPHA, moment=MOMENT)


# ---------------------------------------------------------------------------
# What the publication looks like (ADR 0040)
# ---------------------------------------------------------------------------


def test_an_override_without_an_allocation_publishes_nothing() -> None:
    """A project is deployed before it is published, and the order is forced.

    The allocation key is the instance UUID the volume carries, and on a first
    deploy that UUID does not exist until the cluster has bootstrapped — which
    happens after `compose up`. So the first start publishes nothing, and a
    later privileged render adds it.
    """
    document = runtime_override.build_override(
        router_name="apg-alpha-dev-health",
        rest_router_name="apg-alpha-dev-rest",
        buffering_middleware_name="apg-alpha-dev-api-buffering",
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/alpha-dev",
    )
    assert not [name for name, service in document["services"].items() if "ports" in service]


# ---------------------------------------------------------------------------
# ADR 0044 — nothing is published
#
# Three tests stood here: a publication on a non-loopback address is refused, a
# publication on a privileged port is refused, and the override publishes both
# transports and nothing else. They were correct for a design in which something
# was published, and Run 9 measured that nothing can be: Docker installs no DNAT
# rule and no listener for a container on an `internal: true` network.
#
# What replaces them is strictly stronger. The old pair refused a BAD
# publication; this refuses ANY, including every input the old tests accepted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "port"),
    [
        ("127.0.0.1", 15432),  # the exact pair the old tests accepted
        ("127.0.0.53", 15433),
        ("::1", 15432),
        ("0.0.0.0", 15432),  # noqa: S104 -- an input being refused, not a bind
        ("62.238.99.122", 15432),
        ("127.0.0.1", 443),
        ("", 15432),
    ],
)
def test_no_publication_can_be_built_at_all(address: str, port: int) -> None:
    """ADR 0044. The capability is absent, not merely unused.

    The first three rows are what the superseded design called *correct*: a
    loopback address and an unprivileged port. They are refused here, which is
    what makes this stricter than the tests it replaces rather than a relaxation
    wearing an ADR number.

    Goes red if somebody reintroduces a `ports:` entry for a database transport
    — which would silently do nothing on an internal network, and would do
    something the day the network stopped being internal.
    """
    with pytest.raises(RuntimeError, match="nothing is published"):
        runtime_override.publication(address=address, port=port, container_port=6432)


def test_the_override_carries_no_ports_entry_for_any_service() -> None:
    """The other half: not just that the builder refuses, but that the document
    it builds has no publication in it.

    Goes red if a `ports:` key reaches the runtime override by any route,
    including one that never calls `publication()`.
    """
    payload = runtime_override.render_override(
        router_name="apg-alpha-dev-health",
        rest_router_name="apg-alpha-dev-rest",
        buffering_middleware_name="apg-alpha-dev-api-buffering",
        https_entrypoint="websecure",
        rendered_directory="/var/lib/agentic-postgres/rendered/alpha-dev",
    )
    document = yaml.safe_load(payload)
    for name, service in document["services"].items():
        assert "ports" not in service, f"{name} publishes a port; ADR 0044 says nothing does"
