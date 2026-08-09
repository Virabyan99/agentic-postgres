"""Database endpoint and client compatibility, owned by Session 4 — activated.

Every placeholder this module held was replaced in Session 4 Run 8. They are
gone rather than kept beside their implementations: a placeholder next to a real
test is a second, weaker claim about the same requirement, and
``test_no_requirement_is_claimed_by_two_placeholders`` exists to prevent exactly
that.

  DBX-001..004, DBX-POOL-001..003  -> tests/deployment/test_session4_transports.py
  DBX-005                          -> tests/external/test_session4_public_transports.py

The module itself stays, empty, because ``REQUIRED_PATHS`` is not the only thing
that would notice its absence: the registry's node IDs moved in the same commit,
and a file deleted in a commit that also moves what points at it is a diff nobody
can read. Session 5 fills it again.
"""

from __future__ import annotations
