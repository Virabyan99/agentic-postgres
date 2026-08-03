"""Deterministic, context-aware derivation of project-scoped identities.

Runbook §3.7. This module is load-bearing: every other module consumes it and
none of them may re-derive a name independently.

Implemented in Run 2 of the Session 1 plan, ahead of every consumer, and unit
tested against both fixtures plus synthetic maximum-length inputs before
``rendering.py`` exists.
"""

from __future__ import annotations
