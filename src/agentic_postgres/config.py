"""Strict manifest loading, schema validation, and semantic validation.

Runbook §3.2-§3.6. Holds the authoritative constants named in the plan's
decision log: ``MAX_MANIFEST_BYTES`` (D), ``RESERVED_BASE_PATHS`` and
``paths_overlap`` (B), ``SENSITIVE_KEY_DENYLIST`` and ``SAFE_KEY_ALLOWLIST``
(F). Numeric bounds are *not* here — ``schemas/project.schema.json`` is their
sole authority (E); only cross-field relations live in code.

Implemented in Run 2 of the Session 1 plan.
"""

from __future__ import annotations
