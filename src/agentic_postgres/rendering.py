"""Transactional rendering of generated project outputs.

Runbook §4.1. Stages under ``.generated/.staging/``, validates, then publishes
by directory swap with rollback (plan decision J) under an exclusive per-project
lock (decision I). Refuses symlinked targets and writes owner-only modes.

Implemented in Run 3 of the Session 1 plan.
"""

from __future__ import annotations
