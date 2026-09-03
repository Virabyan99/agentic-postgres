"""The denial taxonomy, and the guard that stops it standing still (ADR 0178).

**The run's real output is the second test in this file**, not the enum. A
vocabulary is easy; what is hard is that a ninth boundary added in Session 18
cannot arrive with no reason attached. That is the way a taxonomy stops covering
its subject — not by being wrong, but by not moving.

Two authorities are kept equal here rather than one being derived from the
other, because neither can be: the enum lives in the catalog, where the database
refuses an unknown value, and the tuple lives in the runtime, where a typo must
be caught before it reaches an audit call. So they are compared, exactly as
`UPSTREAM_WRITE_REFUSALS`'s keys are already compared against migration 0019.
"""

from __future__ import annotations

import re
import sys

import pytest

from agentic_postgres import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "services" / "auth-api"))

from app import mcp_errors

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MIGRATION = REPO_ROOT / "migrations" / "templates" / "0027-agent-audit-denial-taxonomy.sql"

#: The modules that may refuse an agent's call. Named rather than globbed: the
#: claim is about the tool surface and the two things it calls, and a glob over
#: `app/` would sweep in the human endpoints, whose refusals are `errors.py`'s
#: and are not audited here.
REFUSING_MODULES = ("mcp_tools.py", "mcp_errors.py")


def enum_members() -> list[str]:
    """The members migration 0027 declares, in the order it declares them."""
    text = MIGRATION.read_text(encoding="utf-8")
    body = text.split("CREATE TYPE app_private.agent_denial_reason AS ENUM", 1)[1]
    body = body.split(");", 1)[0]
    return re.findall(r"'([a-z_]+)'", body)


def test_the_runtime_vocabulary_is_the_catalogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither file is a second authority (ADR 0002).

    The order matters as well as the set: `DENIAL_REASONS` documents itself as
    being in the enum's own order, and a tuple that had silently reordered would
    make that comment false while every membership assertion still passed.
    """
    declared = enum_members()

    assert declared, "no members were parsed out of migration 0027; the scan is stale"
    assert list(mcp_errors.DENIAL_REASONS) == declared, (
        f"the runtime declares {list(mcp_errors.DENIAL_REASONS)} and migration 0027 "
        f"declares {declared}"
    )


def test_a_reason_the_catalog_does_not_know_is_refused() -> None:
    """`denial_reason` validates where the value is CHOSEN, not at the database.

    The column's type would refuse it anyway — and that refusal arrives as a
    constraint violation *inside an audit call*, which the write path treats as
    `audit_unavailable` and fails closed on. So a misspelled constant would
    surface as "the audit table is broken", which is the wrong diagnosis and the
    expensive kind of wrong.
    """
    for known in mcp_errors.DENIAL_REASONS:
        assert mcp_errors.denial_reason(known) == known

    with pytest.raises(ValueError, match="not a denial reason"):
        mcp_errors.denial_reason("credential")


def test_credential_is_not_a_member_and_the_reason_is_written_down() -> None:
    """D886. The session plan named five members and this is the one that is not real.

    **The MCP runtime holds no credential of any kind**, so the member could not
    describe its own. And if it meant the caller's, `mcp_upstream`'s own header
    measures four states behind two statuses — no Authorization, an unknown
    agent, a forged signature, and a human token — so naming one `credential` is
    D433's forbidden guess, in a durable record read by somebody who cannot
    re-derive what was true.

    Asserted rather than merely omitted, because an absence explains nothing to
    the next person to reach for it.
    """
    assert "credential" not in mcp_errors.DENIAL_REASONS
    assert mcp_errors.UPSTREAM_REFUSED in mcp_errors.DENIAL_REASONS

    migration = MIGRATION.read_text(encoding="utf-8")
    assert "credential" in migration, (
        "migration 0027 no longer says why `credential` is not a member; the "
        "absence is now unexplained and the next session will add it back"
    )


def test_every_token_a_reason_carries_is_one_a_caller_may_see() -> None:
    """The two vocabularies meet in exactly one table, and it is total."""
    assert set(mcp_errors.TOKEN_FOR_REASON) == set(mcp_errors.DENIAL_REASONS), (
        "the reason-to-token table does not cover every reason"
    )

    for reason, token in mcp_errors.TOKEN_FOR_REASON.items():
        if token is None:
            continue
        assert token in mcp_errors.CALLER_FACING_TOKENS, f"{reason} maps to {token!r}"

    # The control: some reasons DO map to a token and some deliberately do not.
    # A table that was all-None, or all-mapped, would pass the loop above and
    # would mean the structural/visible split had collapsed.
    mapped = [token for token in mcp_errors.TOKEN_FOR_REASON.values() if token is not None]
    assert mapped, "no reason reaches a caller; the visible half has been lost"
    assert len(mapped) < len(mcp_errors.TOKEN_FOR_REASON), (
        "every reason reaches a caller, so the structural half has been lost — "
        "which is D433's rule undone"
    )


def test_every_refusal_site_maps_to_exactly_one_denial_reason() -> None:
    """ADR 0178, and **this is what Run 3 is for**.

    A vocabulary is cheap. What this stops is a ninth boundary being added later
    with no reason attached — the way a taxonomy stops covering its subject
    without ever becoming wrong.

    Both refusal types take the reason as a REQUIRED positional argument, so a
    site that omits one is a `TypeError` at import-adjacent test time rather
    than a NULL in a column somebody reads next quarter. This scans for the
    raises and asserts each names a member, which is the half a required
    argument cannot check: `ToolRefusal(STRUCTURAL_REFUSAL, STRUCTURAL_REFUSAL)`
    satisfies the signature and means nothing.
    """
    sites: list[tuple[str, int, str]] = []
    for name in REFUSING_MODULES:
        path = REPO_ROOT / "services" / "auth-api" / "app" / name
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?:raise|return) (AgentVisible|ToolRefusal)\(", text):
            line = text[: match.start()].count("\n") + 1
            # The call's own text, to the matching paren.
            depth, index = 0, match.end() - 1
            while index < len(text):
                if text[index] == "(":
                    depth += 1
                elif text[index] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            sites.append((name, line, text[match.start() : index + 1]))

    assert len(sites) > 15, (
        f"only {len(sites)} refusal site(s) were found across {list(REFUSING_MODULES)}. "
        "The scan has broken, and every assertion below would pass by finding almost "
        "nothing (D509)"
    )

    unnamed = [
        f"{name}:{line} {call.splitlines()[0][:70]}"
        for name, line, call in sites
        if not any(reason.upper() in call for reason in _CONSTANT_NAMES)
    ]
    assert not unnamed, (
        "these refusals name no denial reason, so an operator reading the audit "
        "row would see `refused` and nothing else:\n  " + "\n  ".join(unnamed)
    )


#: The CONSTANT names, not the string values: the sites name constants, and a
#: scan for the values would miss `NOT_IN_ALLOWLIST` while matching a comment
#: that happened to contain `not_in_allowlist`.
_CONSTANT_NAMES = (
    "SCOPE_NOT_HELD_REASON",
    "NOT_IN_ALLOWLIST",
    "INPUT_MALFORMED",
    "BUDGET_EXCEEDED_REASON",
    "CONTRACT_DRIFT",
    "UPSTREAM_REFUSED",
    "AUDIT_UNAVAILABLE",
    "WRITE_REJECTED",
)


def test_the_constant_names_are_the_ones_the_runtime_exports() -> None:
    """Guard the guard: the scan above is only as good as this list.

    A renamed constant would leave `_CONSTANT_NAMES` naming something that no
    longer exists, every site would stop matching, and the scan would report
    every refusal as unnamed — loud, which is the right direction to fail. The
    dangerous direction is a member ADDED to the enum and not to this list,
    which would let its sites pass unchecked, and that is what this catches.
    """
    exported = {
        name
        for name in dir(mcp_errors)
        if name.isupper() and getattr(mcp_errors, name) in mcp_errors.DENIAL_REASONS
    }
    assert set(_CONSTANT_NAMES) <= exported, (
        f"these are scanned for and not exported: {sorted(set(_CONSTANT_NAMES) - exported)}"
    )
    assert len(_CONSTANT_NAMES) == len(mcp_errors.DENIAL_REASONS), (
        f"the scan knows {len(_CONSTANT_NAMES)} constant(s) and the taxonomy has "
        f"{len(mcp_errors.DENIAL_REASONS)} member(s); a member with no constant in "
        "this list is a boundary the site scan cannot see"
    )
