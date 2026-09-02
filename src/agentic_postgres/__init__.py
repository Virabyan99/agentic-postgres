"""Agentic Postgres Primitive — deterministic repository contract.

This package holds the logic that derives every project-scoped identity from a
validated, non-secret manifest. Nothing here reads a secret, opens a network
connection, or starts a service.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Session whose acceptance gate this working tree currently targets.
#: ``APG_ACCEPTANCE_SESSION`` overrides it; see plan decision P. Keeping a
#: default here means a bare ``pytest`` run enforces the same registry policy
#: as ``bin/session-01-check.sh`` instead of silently skipping it.
#:
#: Moved to 6 in Session 6 Run 11 and to 7 in Session 7 Run 9, each time with
#: the placeholders (D54). The move is what makes
#: ``test_no_requirement_at_or_before_the_gate_session_remains_future`` enforce
#: this session's own requirements: every ID targeted at 7 or earlier must now
#: point at a real test rather than at a ``future`` marker, so the eleven
#: entries Run 9 activated cannot quietly revert to placeholders.
#:
#: **This also arms the `session7` Compose profile.** The storage container is
#: held back by that profile, so until this line moved nothing could start one
#: -- and nothing had. A deploy from here on will try to, which means the two R2
#: secrets have to exist at the provider first. That is Run 10's sequence and
#: `docs/session-07-operator-guide.md` is the order to follow.
#:
#: **Session 10, since Run 10.** Moved together with the five recovery
#: placeholders' replacement, which is the pairing D439/D484 requires: the
#: placeholder policy and the overdue policy are exact mirrors on the gate
#: session. The constraint binds one way -- the bump requires the replacements,
#: and not the reverse -- so Run 9 replaced them and this run takes the bump,
#: together with ``bin/session-10-check.sh``. A tree declaring session 10
#: without its gate script is a tree whose gate cannot run (D579).
#:
#: **This arms no new Compose profile**, and that is the difference from every
#: previous bump. Session 10 added none: the archiver lives in the ``session3``
#: postgres service and the backup network is attached unconditionally. What it
#: arms is the deploy's **step 6c**, which creates a stanza and runs
#: ``pgbackrest check`` -- and a check failure fails the deploy. So a deploy from
#: here on needs the three repository secrets present at the provider, and an R2
#: bucket and token an operator created out of band. That is Runs 11+, and
#: ``docs/session-10-operator-guide.md`` is the order to follow.
#:
#: **Session 11 arms no new Compose profile either.** `session_profiles` emits
#: ``--profile session11`` and no service carries it -- exactly as sessions 9 and
#: 10 do, whose profiles compose.yaml also does not define. What Session 11 adds
#: is a step 0 preflight, a deployed `doctor.sh`, one request id stamped on every
#: response, and migration 0022.
#:
#: **It moves in Run 9, not Run 11, and the suite is what decided that** (D672).
#: The plan put the bump in Run 11 and asked Run 9 to redeploy
#: ``--through-session 11`` -- which `deploy.sh` refuses above this number
#: (D59). Two more guards agree: `test_every_later_requirement_has_a_placeholder`
#: keeps a placeholder for any requirement targeting a session past this one, and
#: `test_every_claim_belongs_to_a_session_the_release_has_reached` refuses a
#: claim above it. Activation cannot precede the bump, and the trip cannot
#: precede activation.
#:
#: **Session 13 arms no new Compose profile and adds no service.** What it
#: activates is the release-identity surface: the compatibility rules on
#: `template_version` (ADR 0162), the `upgrade check | plan | verify` verbs, and
#: one front door over the commands that already exist.
#:
#: **The bump is all-or-nothing** (D690).
#: `test_no_requirement_at_or_before_the_gate_session_remains_future` refuses any
#: requirement due by now that is still a placeholder, so all four `REL-*`
#: requirements stop being placeholders in the same commit that moves this.
#:
#: **Session 13 is the first Stage 2 release, and it is where this constant stops
#: being the only version.** `VERSION` moved to `0.2.0` in the same commit and now
#: carries meaning: ADR 0162 says what each bump permits. **Both axes are kept
#: deliberately** (D705) -- this one is the internal release ordinal the evidence
#: model is keyed to, and `template_version` is the product version an operator
#: quotes. Replacing the ordinal would cost a session and buy a number already
#: published under another name.
#:
#: **And moving it is what D719 was waiting for.** `bin/write-session-evidence.py`
#: held `1 <= session <= 12` as a literal -- correct at every check for twelve
#: sessions, because the number it named and the number it meant were the same
#: one. It derives from here now, and so does its `--help`.
CURRENT_SESSION = 14

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


def acceptance_session() -> int:
    """The session whose registry policy is in force, honouring the override.

    **Here rather than in ``tests/conftest.py``, since Session 10 Run 10.** It
    was written there when the tests were its only reader; D526 gave it a second
    one. ``bin/render-acceptance-matrix.py`` hard-coded ``session == 1`` for
    "active", so ``docs/acceptance-matrix.md`` said *"placeholders owned by
    Session 2"* beside thirteen shipped, passing requirements -- a generated
    document asserting the opposite of the tree, which is the drift the generator
    exists to prevent. It said so for nine sessions and nobody read it.

    A second implementation in ``bin/`` would have been the same defect one layer
    up (D264), so the derivation moved here and ``tests/conftest.py`` wraps it.

    Raises ``ValueError`` on a non-integer override, and the caller decides what
    that means: a test run wants ``pytest.UsageError``, a generator wants to exit.
    """
    raw = os.environ.get("APG_ACCEPTANCE_SESSION")
    if raw is None:
        return CURRENT_SESSION
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"APG_ACCEPTANCE_SESSION must be an integer, got {raw!r}") from error


__all__ = ["CURRENT_SESSION", "REPO_ROOT", "acceptance_session", "template_version"]
