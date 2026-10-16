"""Plans and entitlements, read from the auth service's build context (ADR 0274, ADR 0084).

The table lives in `services/auth-api/app/plans.py` because the control mode
serves and enforces it and cannot import `src/`; this module re-exports it for
the repository's readers -- the reconciler's limit notices (ADR 0275) first.
"""

from __future__ import annotations

from agentic_postgres import service_source

_plans = service_source.load("plans")

BETA_SENTENCE: str = _plans.BETA_SENTENCE
DEFAULT_PLAN: str = _plans.DEFAULT_PLAN
ENFORCED_IN_SQL: tuple[str, ...] = _plans.ENFORCED_IN_SQL
PLANS = _plans.PLANS
PLAN_NAMES: tuple[str, ...] = _plans.PLAN_NAMES
Entitlement = _plans.Entitlement
Plan = _plans.Plan

__all__ = [
    "BETA_SENTENCE",
    "DEFAULT_PLAN",
    "ENFORCED_IN_SQL",
    "PLANS",
    "PLAN_NAMES",
    "Entitlement",
    "Plan",
]
