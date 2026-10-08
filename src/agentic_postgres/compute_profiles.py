"""Compute profiles, read from the auth service's build context (ADR 0258, D2156).

The table lives in `services/auth-api/app/compute_profiles.py` because the control
mode validates a resize request's profile name and cannot import `src/` (ADR
0084); this module loads it and adds what only the repository needs: which
manifest members a profile OWNS, and the per-service resource overrides the
render merges over `config.SERVICE_RESOURCE_DEFAULTS`.

`config.apply_compute_profile` is the one place a profile becomes manifest
values -- inside `load_project_manifest`, after the schema and before every
semantic rule -- so every reader of a budget, a pool or a memory limit sees the
profile's numbers exactly as if they had been written, and the validators that
bound them are the ones that already exist.
"""

from __future__ import annotations

from typing import Any

from agentic_postgres import service_source

_profiles = service_source.load("compute_profiles")

PROFILE_NAMES: tuple[str, ...] = _profiles.PROFILE_NAMES
PROFILES: dict[str, dict[str, Any]] = _profiles.PROFILES
RESIZE_WINDOW_SECONDS: int | None = _profiles.RESIZE_WINDOW_SECONDS
UNMEASURED_RESIZE_MESSAGE: str = _profiles.UNMEASURED_RESIZE_MESSAGE
resize_message = _profiles.resize_message

#: What a manifest gets when it names no profile.
DEFAULT_PROFILE = "standard"

__all__ = [
    "DEFAULT_PROFILE",
    "PROFILES",
    "PROFILE_NAMES",
    "RESIZE_WINDOW_SECONDS",
    "UNMEASURED_RESIZE_MESSAGE",
    "owned_members",
    "resize_message",
    "resource_overrides",
    "values",
]


def _paths(node: dict[str, Any], prefix: tuple[str, ...]) -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for key, value in node.items():
        if isinstance(value, dict):
            out += _paths(value, (*prefix, key))
        else:
            out.append((*prefix, key))
    return out


def values(profile: str) -> list[tuple[tuple[str, ...], Any]]:
    """Every manifest member the profile sets, as (path, value), resources excluded."""
    table = {key: value for key, value in PROFILES[profile].items() if key != "resources"}
    out = []
    for path in _paths(table, ()):
        node: Any = table
        for part in path:
            node = node[part]
        out.append((path, node))
    return out


def owned_members() -> tuple[str, ...]:
    """The dotted manifest paths a profile owns -- the same set for every profile,
    read from `standard` (a test holds the three profiles to one shape)."""
    return tuple(".".join(path) for path, _ in values(DEFAULT_PROFILE))


def resource_overrides(profile: str) -> dict[str, dict[str, Any]]:
    """The per-service pids/cpus the profile moves; empty for one that moves none."""
    return {service: dict(members) for service, members in PROFILES[profile]["resources"].items()}
