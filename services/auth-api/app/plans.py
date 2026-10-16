"""Plans and their entitlements: a release table (Session 41, ADR 0274, D2519-D2522).

Lives in the auth service's build context because the control mode serves and
enforces it and cannot import `src/` (ADR 0084); `src/agentic_postgres/plans.py`
re-exports it. **Standard library only.**

`free` is the beta's one active plan; `premium` is defined -- its limits are
served -- and `unavailable_during_beta`: nothing moves an organisation onto it,
and *Notify me* records that a member asked (`app.control_plan_interest`).

**Every entitlement says whether it is enforced and by which reader.** Three
are enforced by the control plane before an operation row exists:
`projects_active` (the organisation's projects not deleted plus its
non-terminal creations; a sleeping project holds its slot and counts),
`branches_total` (a project's recorded live branches plus its non-terminal
branch creations) and `compute_profiles` (the profile names a request may
carry). Two are READ, never enforced, and say so: `storage_gb` (no per-project
disk quota exists, D1955) and `agent_calls_per_day` (the control plane holds no
path to a project's agents, ADR 0246, D2520). The retention is a sentence: it
is what the deployed repository does (`repo1-retention-full` 2).

The numbers and their reasons are ADR 0274's table. `app.control_plan_limits`,
seeded by the control set's `0008`, is held equal to this table by
`tests/contract/test_plans.py::test_the_sql_limits_are_the_release_table`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "BETA_SENTENCE",
    "DEFAULT_PLAN",
    "ENFORCED_IN_SQL",
    "PLANS",
    "PLAN_NAMES",
    "Entitlement",
    "Plan",
]

#: The plans, in the order they are listed.
PLAN_NAMES: tuple[str, ...] = ("free", "premium")
#: An organisation's plan until something moves it -- nothing does in the beta.
DEFAULT_PLAN: Final = "free"

#: Said beside every plan the beta serves (D2522).
BETA_SENTENCE: Final = (
    "Free is the plan every organisation has during the beta. Premium is defined and not "
    "available during the beta: its limits are shown, and Notify me records that you asked. "
    "Nothing is charged."
)


@dataclass(frozen=True)
class Entitlement:
    """One limit of a plan: its value, whether anything enforces it, and the
    reader that enforces or shows it. `value` is an integer, a tuple of names,
    or a sentence; `unit` says which."""

    value: int | tuple[str, ...] | str
    unit: str
    enforced: bool
    reader: str


@dataclass(frozen=True)
class Plan:
    name: str
    status: str
    entitlements: dict[str, Entitlement]


_PROFILES: tuple[str, ...] = ("small", "standard", "large")

PLANS: dict[str, Plan] = {
    "free": Plan(
        name="free",
        status="active",
        entitlements={
            "projects_active": Entitlement(1, "projects", True, "control plane"),
            "branches_total": Entitlement(1, "branches per project", True, "control plane"),
            "compute_profiles": Entitlement(_PROFILES, "profiles", True, "control plane"),
            "storage_gb": Entitlement(5, "GB of database", False, "usage"),
            "agent_calls_per_day": Entitlement(10_000, "agent calls per day", False, "usage"),
            "backup_retention": Entitlement(
                "two weekly full backups and the WAL between them", "text", True, "the deploy"
            ),
        },
    ),
    "premium": Plan(
        name="premium",
        status="unavailable_during_beta",
        entitlements={
            "projects_active": Entitlement(3, "projects", True, "control plane"),
            "branches_total": Entitlement(3, "branches per project", True, "control plane"),
            "compute_profiles": Entitlement(_PROFILES, "profiles", True, "control plane"),
            "storage_gb": Entitlement(20, "GB of database", False, "usage"),
            "agent_calls_per_day": Entitlement(100_000, "agent calls per day", False, "usage"),
            "backup_retention": Entitlement("planned", "text", False, "planned"),
        },
    ),
}

#: The two entitlements `app.control_request_operation` reads from
#: `app.control_plan_limits` under the organisation's lock (D2521, D2538).
ENFORCED_IN_SQL: tuple[str, ...] = ("projects_active", "branches_total")
