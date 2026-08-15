"""Agentic Postgres Primitive — deterministic repository contract.

This package holds the logic that derives every project-scoped identity from a
validated, non-secret manifest. Nothing here reads a secret, opens a network
connection, or starts a service.
"""

from __future__ import annotations

from pathlib import Path

#: Session whose acceptance gate this working tree currently targets.
#: ``APG_ACCEPTANCE_SESSION`` overrides it; see plan decision P. Keeping a
#: default here means a bare ``pytest`` run enforces the same registry policy
#: as ``bin/session-01-check.sh`` instead of silently skipping it.
#:
#: Moved to 6 in Session 6 Run 11, with the placeholders (D54). The move is what
#: makes ``test_no_requirement_at_or_before_the_gate_session_remains_future``
#: enforce this session's own requirements: every ID targeted at 6 or earlier
#: must now point at a real test rather than at a ``future`` marker, so the
#: eleven entries this run activated cannot quietly revert to placeholders.
CURRENT_SESSION = 6

#: Repository root, resolved from this file rather than the caller's cwd so
#: that scripts and tests behave identically when invoked from anywhere
#: (runbook §8.5, "scripts work when invoked outside the repository root").
REPO_ROOT = Path(__file__).resolve().parents[2]


def template_version() -> str:
    """Return the template version.

    ``VERSION`` at the repository root is the single source of truth for
    ``outputs.json.template_version`` (plan decision G).
    """
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


__all__ = ["CURRENT_SESSION", "REPO_ROOT", "template_version"]
