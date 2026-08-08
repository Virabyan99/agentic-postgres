"""Host-loopback port allocation, keyed by the identity the volume carries.

ADR 0042. Two ports per project, one per transport, durable across redeploy,
restart and reboot — because an allocation that moves silently breaks every
developer's saved tunnel and every documented command, and does it without an
error message anywhere: the port is simply somebody else's now, or nobody's.

**The key is `app_private.project_identity.instance_uuid`**, which the cluster
generates once on the first bootstrap of an empty volume and recovers on every
bootstrap since. It is the only identifier in this system bound to the *data*
rather than to the configuration that produced it, so a restored volume brings
its allocation's identity with it. The project key is recorded for humans and is
never matched on: two projects can share a key across a rebuild, and one project
can change it.

This module is deliberately pure. It reads and writes no file, opens no socket
and takes no lock; it transforms a registry document into another registry
document and raises when it cannot. That is what makes the interesting cases —
a duplicate port, a reservation adopted as active, a range too small — testable
without root, without a host, and without a cluster.

The two invariants JSON Schema cannot state live here, and they are the two that
matter most:

* **no two live allocations share a port**, which `uniqueItems` cannot express
  because it compares whole objects, so two allocations differing only in a
  timestamp satisfy it while claiming the same port;
* **no two allocations share an instance UUID**, for the same reason.

`tests/contract/test_port_allocations.py` asserts that the *schema* accepts both
of those, deliberately, so the boundary between what validation covers and what
this module must is written down rather than assumed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from agentic_postgres import config

#: Lowercase only, matching the schema. Normalising instead would make two
#: spellings of one identity comparable here and different everywhere else.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

__all__ = [
    "PORTS_PER_PROJECT",
    "REGISTRY_PATH",
    "SCHEMA_NAME",
    "AllocationError",
    "activate",
    "allocate",
    "empty_registry",
    "find",
    "live_allocations",
    "release",
    "taken_ports",
    "timestamp",
    "validate",
]

#: Host-global state, following `edge-state.json` as the precedent (ADR 0020).
REGISTRY_PATH = "/etc/agentic-postgres/database-port-allocations.json"

SCHEMA_NAME = "database-port-allocations.schema.json"

#: One pooled, one direct (ADR 0041). Allocated together or not at all.
PORTS_PER_PROJECT = 2

#: The states in which an allocation still owns its ports. A released record
#: keeps its ports written down — that is the audit trail — but does not hold
#: them against anyone else.
LIVE_STATES = frozenset({"reserved", "active"})


class AllocationError(ValueError):
    """The registry, or the request, is not one this module will act on."""


def timestamp(moment: datetime | None = None) -> str:
    """UTC, second resolution, Z-suffixed: the shape the schema admits."""
    return (moment or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty_registry() -> dict[str, Any]:
    """What a host with no project deployed has.

    A file rather than an absence, so that "no file" stays unambiguous: it means
    state was lost, not that nothing is allocated, and those need different
    responses.
    """
    return {"schema_version": 1, "allocations": []}


def validate(registry: dict[str, Any]) -> dict[str, Any]:
    """Schema first, then the two relations the schema cannot state.

    Called before every mutation and after every load. A registry that fails
    here is never partially repaired: the ports in it are bound by running
    containers, and a repair that guessed which allocation was wrong would move
    a port out from under one of them.
    """
    config.validate_against_schema(registry, SCHEMA_NAME)

    identities: dict[str, int] = {}
    for index, allocation in enumerate(registry["allocations"]):
        uuid = allocation["instance_uuid"]
        if uuid in identities:
            raise AllocationError(
                f"instance {uuid} appears in allocations {identities[uuid]} and {index}. "
                "One volume has one allocation; two records for it means one of them "
                "is describing ports nothing holds"
            )
        identities[uuid] = index

    # Self-collision first, or the cross-allocation check below reports it as
    # one identity colliding with itself -- true, and useless to read.
    for allocation in registry["allocations"]:
        if allocation["pooled_port"] == allocation["direct_port"]:
            raise AllocationError(
                f"{allocation['instance_uuid']} has one port for both transports "
                f"({allocation['pooled_port']}); they are two listeners"
            )

    owners: dict[int, str] = {}
    for allocation in registry["allocations"]:
        if allocation["state"] not in LIVE_STATES:
            continue
        for port in (allocation["pooled_port"], allocation["direct_port"]):
            if port in owners:
                raise AllocationError(
                    f"port {port} is claimed by both {owners[port]} and "
                    f"{allocation['instance_uuid']}. Two projects cannot both be "
                    "reachable on it, and the one that loses is decided by whichever "
                    "container started second"
                )
            owners[port] = allocation["instance_uuid"]

    return registry


def live_allocations(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in registry["allocations"] if a["state"] in LIVE_STATES]


def taken_ports(registry: dict[str, Any], *, excluding: str | None = None) -> set[int]:
    """Every port a live allocation holds, optionally ignoring one identity."""
    return {
        port
        for allocation in live_allocations(registry)
        if allocation["instance_uuid"] != excluding
        for port in (allocation["pooled_port"], allocation["direct_port"])
    }


def find(registry: dict[str, Any], instance_uuid: str) -> dict[str, Any] | None:
    for allocation in registry["allocations"]:
        if allocation["instance_uuid"] == instance_uuid:
            return allocation
    return None


def allocate(
    registry: dict[str, Any],
    *,
    instance_uuid: str,
    project_key: str,
    port_range: tuple[int, int],
    usable: set[int] | None = None,
    moment: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reserve two ports for one identity, or return the two it already has.

    Reuse is the default and idempotence is the point: a redeploy calls this and
    must get back the same two numbers, because they are in somebody's saved
    tunnel. An existing `reserved` or `active` allocation is returned unchanged,
    including its state — this function never promotes, because promotion is
    what `activate` does after the endpoint checks pass, and a function that did
    both would make a crashed deploy indistinguishable from a verified one.

    A *released* allocation for this identity is re-reserved **on its original
    ports** when they are still free. That is the restored-volume case, and it
    is the reason the key is the volume's UUID rather than a fresh one: the
    developer's saved tunnel still works after a restore.

    ``usable`` is the set of ports the caller has proved bindable. It is a
    parameter rather than a probe because this module opens no socket, and
    because the check has to happen under the same lock as the write — a port
    that was free when probed and taken when written is the race the lock
    exists for.
    """
    validate(registry)

    if not _UUID.fullmatch(instance_uuid):
        raise AllocationError(
            f"instance_uuid is not a lowercase UUID: {instance_uuid!r}. Two spellings "
            "of one identity is two identities to whatever compares them as strings"
        )

    existing = find(registry, instance_uuid)
    if existing is not None and existing["state"] in LIVE_STATES:
        return registry, existing

    low, high = port_range
    if low >= high:
        raise AllocationError(f"port range {low}-{high} does not run upwards")

    taken = taken_ports(registry, excluding=instance_uuid)
    candidates = [port for port in range(low, high + 1) if port not in taken]
    if usable is not None:
        candidates = [port for port in candidates if port in usable]

    if existing is not None:
        # A released allocation whose ports are still free keeps them.
        wanted = [existing["pooled_port"], existing["direct_port"]]
        if all(port in candidates for port in wanted):
            chosen = wanted
        else:
            raise AllocationError(
                f"{project_key} was released holding {wanted[0]} and {wanted[1]}, and "
                "at least one of those is no longer available. Re-allocating it onto "
                "different ports would silently break every saved tunnel and every "
                "documented command; remove the released record deliberately if that "
                "is what you mean"
            )
    else:
        if len(candidates) < PORTS_PER_PROJECT:
            raise AllocationError(
                f"{len(candidates)} usable ports in {low}-{high}; a project needs "
                f"{PORTS_PER_PROJECT} and they are allocated together"
            )
        chosen = candidates[:PORTS_PER_PROJECT]

    now = timestamp(moment)
    allocation = {
        "instance_uuid": instance_uuid,
        "project_key": project_key,
        "pooled_port": chosen[0],
        "direct_port": chosen[1],
        "state": "reserved",
        "reserved_at": now,
        "activated_at": None,
        "released_at": None,
    }

    allocations = [a for a in registry["allocations"] if a["instance_uuid"] != instance_uuid]
    allocations.append(allocation)
    updated = {**registry, "allocations": allocations}
    validate(updated)
    return updated, allocation


def activate(
    registry: dict[str, Any], *, instance_uuid: str, moment: datetime | None = None
) -> dict[str, Any]:
    """Promote a reservation, and only after somebody checked the endpoints.

    Separate from :func:`allocate` on purpose. A crashed first deploy leaves a
    reservation, which can be proved unadopted; if allocation promoted itself,
    the registry would say a port was serving traffic because a process once
    intended it to.
    """
    validate(registry)

    allocation = find(registry, instance_uuid)
    if allocation is None:
        raise AllocationError(f"no allocation for instance {instance_uuid}")
    if allocation["state"] == "active":
        return registry
    if allocation["state"] != "reserved":
        raise AllocationError(
            f"instance {instance_uuid} is {allocation['state']}, not reserved; "
            "only a reservation becomes active"
        )

    promoted = {**allocation, "state": "active", "activated_at": timestamp(moment)}
    allocations = [
        promoted if a["instance_uuid"] == instance_uuid else a for a in registry["allocations"]
    ]
    return validate({**registry, "allocations": allocations})


def release(
    registry: dict[str, Any],
    *,
    instance_uuid: str,
    project_key: str,
    moment: datetime | None = None,
) -> dict[str, Any]:
    """Give up two ports, with the identity confirmed rather than assumed.

    ``project_key`` is required and must match what the record says. It is the
    only argument here that is not the match key, and that is exactly why it is
    demanded: releasing is the one operation that can hand a developer's port to
    another project, so the caller has to name the thing they think they are
    releasing and be told when they are wrong.
    """
    validate(registry)

    allocation = find(registry, instance_uuid)
    if allocation is None:
        raise AllocationError(f"no allocation for instance {instance_uuid}")
    if allocation["project_key"] != project_key:
        raise AllocationError(
            f"instance {instance_uuid} is recorded as {allocation['project_key']!r}, "
            f"not {project_key!r}. Refusing to release an allocation the caller has "
            "misidentified"
        )
    if allocation["state"] == "released":
        return registry

    released = {**allocation, "state": "released", "released_at": timestamp(moment)}
    allocations = [
        released if a["instance_uuid"] == instance_uuid else a for a in registry["allocations"]
    ]
    return validate({**registry, "allocations": allocations})
