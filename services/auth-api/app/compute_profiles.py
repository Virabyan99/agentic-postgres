"""Compute profiles: named sets of values a project manifest can already carry (ADR 0258).

Lives in the auth service's build context because the control mode validates a
resize request's profile NAME and cannot import `src/` (ADR 0084);
`src/agentic_postgres/compute_profiles.py` loads it through `service_source` and
applies a profile to a manifest. **Standard library only** -- `config.py` reads
this on a deploy host with nothing else installed.

Every value here is one a deploy already enforces (the memory relation, the auth
floor, the connection budget summed over six claimants); none is new. `standard`
is today's defaults exactly. `small` and `large` were derived on the CX23 from
Sheet E0's readings (2026-10-07) and validated by the product's own validators in
rig 38c' -- ADR 0258 has the table and the readings. A profile changes what
admission CHARGES (`unreclaimable_mb`: 192 / 304 / 840 MiB) and the ceilings; it
cannot make a project small in resident memory, because most of that is seven
processes no profile member moves (D2193).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "CUSTOMER_CONNECTIONS",
    "PROFILES",
    "PROFILE_NAMES",
    "RESIZE_WINDOW_SECONDS",
    "UNMEASURED_RESIZE_MESSAGE",
    "resize_message",
]

#: Every profile, in size order. The control mode refuses any other name.
PROFILE_NAMES: tuple[str, ...] = ("small", "standard", "large")

#: The members each profile sets, in the manifest's own shape. `resources` is a
#: partial map over the per-service pids/cpus defaults: only what a profile
#: MOVES is named (`small` gives postgres one core of two); every other
#: `pids_limit` and `cpus` stays the measured default in all three, because a
#: profile has no measurement to move them by (ADR 0244).
PROFILES: dict[str, dict[str, Any]] = {
    "small": {
        "database": {
            "shared_buffers_mb": 64,
            "maintenance_work_mem_mb": 32,
            "max_connections": 48,
            "work_mem_mb": 4,
            "memory_limit_mb": 512,
            "shm_size_mb": 128,
        },
        "api": {"app": {"memory_limit_mb": 384, "pool_size": 2}, "rest": {"pool_size": 6}},
        "storage": {"memory_limit_mb": 384, "pool_size": 2},
        "resources": {"postgres": {"cpus": "1.0"}},
    },
    "standard": {
        "database": {
            "shared_buffers_mb": 128,
            "maintenance_work_mem_mb": 64,
            "max_connections": 56,
            "work_mem_mb": 4,
            "memory_limit_mb": 768,
            "shm_size_mb": 256,
        },
        "api": {"app": {"memory_limit_mb": 384, "pool_size": 4}, "rest": {"pool_size": 10}},
        "storage": {"memory_limit_mb": 384, "pool_size": 4},
        "resources": {},
    },
    "large": {
        "database": {
            "shared_buffers_mb": 512,
            "maintenance_work_mem_mb": 128,
            "max_connections": 100,
            "work_mem_mb": 4,
            "memory_limit_mb": 1536,
            "shm_size_mb": 768,
        },
        "api": {"app": {"memory_limit_mb": 512, "pool_size": 6}, "rest": {"pool_size": 16}},
        "storage": {"memory_limit_mb": 512, "pool_size": 6},
        "resources": {},
    },
}

#: Session 39 (ADR 0269, D2358): each profile's two CUSTOMER claimants on
#: `max_connections` -- what the transaction-mode customer pooler (`pool`,
#: `customer_app`) and the session-mode one (`direct`, `customer_admin`) may hold
#: on the cluster, each pooler's `max_db_connections` and each role's `CONNECTION
#: LIMIT`. Charged only for a project with public endpoints. Beside `PROFILES`,
#: not in it: every member of a profile there is a MANIFEST member the profile
#: writes in, and these are not. Rig 39e, through the product's own arithmetic
#: with the slot's pool_size 16: small and standard fit 2/2 and not 3/3 (the
#: application's remainder would fall to 15); large fits up to 8/8.
CUSTOMER_CONNECTIONS: dict[str, dict[str, int]] = {
    "small": {"pool": 2, "direct": 2},
    "standard": {"pool": 2, "direct": 2},
    "large": {"pool": 5, "direct": 5},
}

#: The restart a resize causes, in seconds, as MEASURED on this server -- or
#: None while no envelope row exists (D2157). Set at Session 38's close from the
#: trip's resize row (`capacity.ENVELOPE`: the operation's deploy step, an upper
#: bound on the restart -- 70.5 s at 1.16.0), and moved at Session 39's close to
#: 1.17.0's larger step (83.5 s on apg-ovh-01, standard -> large; D2419); a test
#: holds the two equal. Never a guess: with no row the message below says the
#: window is unmeasured rather than print a number nobody read.
RESIZE_WINDOW_SECONDS: int | None = 84

UNMEASURED_RESIZE_MESSAGE = (
    "Resizing restarts the database and the services that use it; "
    "the restart has not been measured on this server yet."
)


def resize_message(window_seconds: int | None = RESIZE_WINDOW_SECONDS) -> str:
    """What a customer is told before a resize: the measured window, or that
    there is none yet (D1976, D2157)."""
    if window_seconds is None:
        return UNMEASURED_RESIZE_MESSAGE
    return (
        "Resizing restarts the database and the services that use it; "
        f"measured on this server, the restart takes about {window_seconds} seconds."
    )
