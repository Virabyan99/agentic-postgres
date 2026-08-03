"""Session evidence assembled from machine-readable test artifacts.

Runbook §4.7 and Phase 12. Reads the JUnit XML and P0 collection artifacts,
the acceptance registry, and the rendered outputs. It fails rather than guess
when a required input cannot be parsed, and it records the tested clean source
commit rather than attempting an impossible self-reference.

Implemented in Run 5 of the Session 1 plan.
"""

from __future__ import annotations
