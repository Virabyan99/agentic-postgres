"""The host port-allocation registry's schema (ADR 0042, Session 4 Run 2).

This file is the durable answer to "which two ports are this project's", and an
allocation that moves silently breaks every saved tunnel and every documented
command without producing an error anywhere. So the schema is written to make
the states that would allow that unrepresentable, and these tests are mostly
negative: what the file may not say matters more than what it may.

Two properties deliberately are *not* here, because JSON Schema cannot state
them and pretending otherwise would be worse than leaving them to Run 4:

* no two allocations may share a port;
* no two may share an instance UUID.

`uniqueItems` looks like it covers the second one and does not — it compares
whole objects, so two allocations differing only in a timestamp while claiming
the same UUID satisfy it. The schema says so in its own description, and the
allocator enforces both under the host lock.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentic_postgres import config
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SCHEMA = "database-port-allocations.schema.json"

UUID_A = "0f9d2c31-5b7e-4a1f-9c33-8de1b4f60a72"
UUID_B = "b55f9932-6c35-453e-9f7e-887b2cb6db88"


def allocation(**overrides: Any) -> dict[str, Any]:
    base = {
        "instance_uuid": UUID_A,
        "project_key": "fixture-alpha-dev",
        "pooled_port": 15432,
        "direct_port": 15433,
        "state": "active",
        "reserved_at": "2026-08-08T12:00:00Z",
        "activated_at": "2026-08-08T12:00:05Z",
        "released_at": None,
    }
    base.update(overrides)
    return base


def registry(*allocations: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "allocations": list(allocations)}


def validate(document: dict[str, Any]) -> None:
    config.validate_against_schema(document, SCHEMA)


# ---------------------------------------------------------------------------
# What a valid registry looks like
# ---------------------------------------------------------------------------


def test_an_empty_registry_is_valid() -> None:
    """A host with no project deployed yet has a file, not an absence.

    The alternative — create the file on first allocation — makes "no file"
    ambiguous between "nothing allocated" and "state was lost", and those two
    need different responses.
    """
    validate(registry())


def test_two_projects_with_distinct_ports_are_valid() -> None:
    validate(
        registry(
            allocation(),
            allocation(
                instance_uuid=UUID_B,
                project_key="fixture-beta-dev",
                pooled_port=15434,
                direct_port=15435,
            ),
        )
    )


@pytest.mark.parametrize(
    "state_fields",
    [
        pytest.param(
            {"state": "reserved", "activated_at": None, "released_at": None}, id="reserved"
        ),
        pytest.param(
            {"state": "active", "activated_at": "2026-08-08T12:00:05Z", "released_at": None},
            id="active",
        ),
        pytest.param(
            {
                "state": "released",
                "activated_at": "2026-08-08T12:00:05Z",
                "released_at": "2026-08-09T09:00:00Z",
            },
            id="released",
        ),
    ],
)
def test_each_state_validates_with_its_own_timestamps(state_fields: dict[str, Any]) -> None:
    validate(registry(allocation(**state_fields)))


# ---------------------------------------------------------------------------
# The states that must be unrepresentable
# ---------------------------------------------------------------------------


def test_a_reservation_may_not_carry_an_activation_time() -> None:
    """`reserved` is the state a crashed first deploy leaves behind.

    It has to stay distinguishable from `active`, because the whole point of the
    two-phase transition is that a reservation can be proved unadopted. An
    activation timestamp on a reservation makes the two indistinguishable to
    anything reading the file rather than the state field.
    """
    with pytest.raises(ManifestError):
        validate(registry(allocation(state="reserved", activated_at="2026-08-08T12:00:05Z")))


def test_an_active_allocation_must_carry_an_activation_time() -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(state="active", activated_at=None)))


def test_an_active_allocation_may_not_be_released() -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(state="active", released_at="2026-08-09T09:00:00Z")))


def test_a_released_allocation_must_say_when() -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(state="released", released_at=None)))


@pytest.mark.parametrize("port", [22, 80, 443, 1023, 0, -1, 65536])
def test_a_privileged_or_impossible_port_is_refused(port: int) -> None:
    """A registry that can express 22 is a registry that can be asked to take it."""
    with pytest.raises(ManifestError):
        validate(registry(allocation(pooled_port=port)))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("0F9D2C31-5B7E-4A1F-9C33-8DE1B4F60A72", id="uppercase"),
        pytest.param("not-a-uuid", id="not-a-uuid"),
        pytest.param("0f9d2c315b7e4a1f9c338de1b4f60a72", id="unhyphenated"),
        pytest.param("", id="empty"),
    ],
)
def test_an_unusable_instance_uuid_is_refused(value: str) -> None:
    """Uppercase is refused rather than normalised, and that is the point.

    Two spellings of one UUID is two identities to whatever compares them as
    strings, and the comparison that matters happens in a shell script under a
    lock. One spelling is admissible.
    """
    with pytest.raises(ManifestError):
        validate(registry(allocation(instance_uuid=value)))


def test_an_unknown_state_is_refused() -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(state="pending")))


def test_an_allocation_missing_a_transport_is_refused() -> None:
    """Both ports are allocated as one transaction, so both are required.

    A project with a pooled port and no direct port is a state nothing knows how
    to converge: it is not unallocated and it is not usable.
    """
    incomplete = allocation()
    del incomplete["direct_port"]
    with pytest.raises(ManifestError):
        validate(registry(incomplete))


def test_an_unknown_member_is_refused() -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(notes="temporary, will remove")))


def test_an_unknown_schema_version_is_refused() -> None:
    with pytest.raises(ManifestError):
        validate({"schema_version": 2, "allocations": []})


@pytest.mark.parametrize(
    "timestamp",
    [
        pytest.param("2026-08-08 12:00:00", id="space-separated"),
        pytest.param("2026-08-08T12:00:00+00:00", id="offset-not-z"),
        pytest.param("2026-08-08T12:00:00.123Z", id="sub-second"),
        pytest.param("1754654400", id="epoch"),
    ],
)
def test_a_timestamp_in_another_shape_is_refused(timestamp: str) -> None:
    with pytest.raises(ManifestError):
        validate(registry(allocation(reserved_at=timestamp)))


# ---------------------------------------------------------------------------
# What the schema cannot say, said out loud
# ---------------------------------------------------------------------------


def test_the_schema_admits_a_duplicate_port_and_says_so() -> None:
    """A green test that documents a gap rather than hiding one.

    Two allocations sharing a port is the single worst thing this file can say,
    and JSON Schema cannot forbid it: `uniqueItems` compares whole objects, so
    two allocations that differ anywhere else satisfy it. Asserting that the
    schema *accepts* this is uncomfortable and correct — it fixes the boundary
    between what validation covers and what the allocator must, so that Run 4
    cannot mistake a validated file for a checked one.
    """
    validate(
        registry(
            allocation(),
            allocation(instance_uuid=UUID_B, project_key="fixture-beta-dev", direct_port=15436),
        )
    )


def test_the_schema_admits_one_uuid_twice_and_says_so() -> None:
    """The same gap from the other direction, for the same reason."""
    validate(
        registry(
            allocation(),
            allocation(pooled_port=15434, direct_port=15435, reserved_at="2026-08-09T12:00:00Z"),
        )
    )
