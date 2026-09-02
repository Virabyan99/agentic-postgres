"""The session plane's state and its pure state machine (Session 15 Run 2).

Migration 0023 holds the state; `agentic_postgres.refresh_sessions` holds what a
presented token *means*. These are the assertions that do not need a database --
the ones that do are Run 3's, against a live deployment, because reuse detection
is a property of two requests arriving in sequence against one row and an offline
proof of it would be a proof about a fixture.

**What was measured against the pinned image rather than asserted here** (ADR
0171, D826/D827): that two concurrent presentations resolve to one winner and an
empty result for the loser under `read committed`, with the loser blocking until
the winner commits; that `repeatable read` raises 40001 for the same statement;
and that the partial unique index refuses `insert-then-consume` with 23505 while
accepting `consume-then-insert`. The rig that established those had a control
proving it had a real race, and the migration that ships was applied by a server
and re-asked the same questions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT
from app import refresh_sessions
from app.refresh_sessions import Outcome, TokenState, classify

pytestmark = [pytest.mark.contract, pytest.mark.p0]

MIGRATION = REPO_ROOT / "migrations" / "templates" / "0023-refresh-session-plane.sql"


@pytest.fixture(scope="module")
def migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------

NOW = 1_000_000


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (TokenState(found=False), Outcome.UNKNOWN),
        (TokenState(found=True, expires_at=NOW + 60), Outcome.ROTATE),
        (TokenState(found=True, consumed=True, expires_at=NOW + 60), Outcome.REUSE),
        (TokenState(found=True, family_revoked=True, expires_at=NOW + 60), Outcome.REVOKED),
        (TokenState(found=True, expires_at=NOW - 1), Outcome.EXPIRED),
        (TokenState(found=True, expires_at=NOW), Outcome.EXPIRED),
    ],
    ids=["unknown", "rotate", "reuse", "revoked", "expired", "expired-exactly-now"],
)
def test_each_state_classifies_to_one_outcome(state: TokenState, expected: Outcome) -> None:
    """The five outcomes, one row each, including the boundary.

    `expires_at == now` is EXPIRED rather than ROTATE: the comparison is `<=`,
    so a deadline is a moment the token is already past rather than one it is
    still inside.
    """
    assert classify(state, now=NOW) is expected


def test_a_replay_outranks_a_revocation_because_it_is_the_alarm() -> None:
    """The precedence that carries the plane's whole purpose.

    A consumed token presented against a family that is ALREADY revoked is a
    second replay, and it is evidence. Classifying it as `REVOKED` -- which is
    what a condition order that checked the family first would do -- would
    suppress exactly the signal reuse detection exists to raise, and it would do
    so precisely in the case where somebody is actively replaying a stolen
    chain.

    Both fields are true here, so this fails if the order in `classify` is
    swapped, and it cannot pass by accident.
    """
    both = TokenState(found=True, consumed=True, family_revoked=True, expires_at=NOW + 60)
    assert classify(both, now=NOW) is Outcome.REUSE


def test_an_unknown_token_is_not_a_replay() -> None:
    """`UNKNOWN` outranks everything, and the distinction is not cosmetic.

    A value nobody issued is a guess. Treating it as reuse would let anyone
    revoke a family -- or fill an operator's alarm channel -- by posting
    arbitrary strings, which is a denial of service wearing the shape of a
    security control.
    """
    assert classify(TokenState(found=False), now=NOW) is Outcome.UNKNOWN
    assert classify(TokenState(found=False, consumed=True), now=NOW) is Outcome.UNKNOWN


def test_classify_reads_no_clock_of_its_own() -> None:
    """`now` is a parameter, so the same state has one answer for a given moment.

    The database's `now()` is the authority (ADR 0171). A function that read a
    clock could not be enumerated in a test, and would be a second authority for
    the moment the row is compared against.
    """
    live = TokenState(found=True, expires_at=NOW + 10)
    assert classify(live, now=NOW) is Outcome.ROTATE
    assert classify(live, now=NOW + 11) is Outcome.EXPIRED


# ---------------------------------------------------------------------------
# Minting
# ---------------------------------------------------------------------------


def test_a_minted_token_is_wellformed_and_its_digest_is_what_is_stored() -> None:
    token, digest = refresh_sessions.mint()
    assert refresh_sessions.is_wellformed(token)
    assert digest == refresh_sessions.hash_token(token)
    assert re.fullmatch(r"[0-9a-f]{64}", digest), "the digest is not the shape 0023 CHECKs for"
    assert token not in digest


def test_two_mints_do_not_collide() -> None:
    """Weak as a randomness test and strong as a wiring test.

    It fails on the mistake that actually happens -- a module-level constant, a
    cached value, a seeded generator -- rather than on a statistical property no
    unit test can establish.
    """
    tokens = {refresh_sessions.mint()[0] for _ in range(64)}
    assert len(tokens) == 64


def test_a_token_this_plane_could_not_have_minted_is_refused_before_a_query() -> None:
    for candidate in [
        "",
        "short",
        "a" * 42,
        "a" * 44,
        "has spaces in it" + "a" * 27,
        "a/b" + "c" * 40,
    ]:
        assert not refresh_sessions.is_wellformed(candidate), candidate


def test_the_digest_is_deterministic_because_the_row_is_found_by_it() -> None:
    """The property that decides SHA-256 over argon2 (ADR 0171, D828).

    A refresh token is presented alone, so the row is found BY this value. A
    salted hash would produce a different digest for the same token every time,
    and the lookup would match nothing -- which is why the two neighbouring
    credential tables can use argon2 and this one cannot.
    """
    token, _ = refresh_sessions.mint()
    assert refresh_sessions.hash_token(token) == refresh_sessions.hash_token(token)


# ---------------------------------------------------------------------------
# The module and the migration are one enumeration
# ---------------------------------------------------------------------------


def test_the_revocation_reasons_match_the_type_the_migration_creates(migration: str) -> None:
    """`jwt_claims.sql_required_claims()` against 0011's literal, for this enum.

    Two spellings of one enumeration is how they come to disagree, and the
    failure mode is quiet: the service would write a reason the type does not
    carry and the INSERT would raise 22P02 at the moment somebody logged out.
    """
    body = re.search(
        r"CREATE TYPE app_private\.refresh_revocation AS ENUM \((.*?)\);",
        migration,
        re.DOTALL,
    )
    assert body, "0023 no longer creates app_private.refresh_revocation"

    declared = re.findall(r"'([a-z_]+)'", body.group(1))
    assert declared == list(refresh_sessions.FAMILY_REVOCATION_REASONS), (
        "the migration's enum and refresh_sessions disagree"
    )
    assert body.group(1).strip() == refresh_sessions.sql_revocation_reasons().strip()


def test_reuse_detected_is_one_of_the_reasons_a_family_can_end() -> None:
    """The alarm has somewhere to be recorded.

    `classify` can return `REUSE`, and if the enum carried no matching reason the
    revocation it triggers would have to be written as something else -- which
    would make the column unable to distinguish the case it exists for.
    """
    assert refresh_sessions.RevocationReason.REUSE_DETECTED.value in (
        refresh_sessions.FAMILY_REVOCATION_REASONS
    )


# ---------------------------------------------------------------------------
# What the migration must and must not contain
# ---------------------------------------------------------------------------


def test_the_migration_issues_no_grant_because_its_caller_does_not_exist_yet(
    migration: str,
) -> None:
    """0011's rule, applied to its own successor (D830).

    *"A grant issued now would be a grant nobody can audit against a caller that
    does not exist."* The endpoints are Run 3, so the SECURITY DEFINER functions
    and their grants are Run 3. This goes red the moment somebody adds a grant
    here without the code that uses it.
    """
    grants = [
        line.strip()
        for line in migration.splitlines()
        if re.match(r"^\s*GRANT\b", line) and not line.strip().startswith("--")
    ]
    assert not grants, f"0023 issues grants but has no caller yet: {grants}"

    functions = re.findall(r"^\s*CREATE (?:OR REPLACE )?FUNCTION", migration, re.MULTILINE)
    assert not functions, "0023 creates a function; the functions arrive with their caller"


def test_the_one_live_token_invariant_is_in_the_catalog_not_in_a_comment(
    migration: str,
) -> None:
    """The partial unique index reuse detection rests on (ADR 0171).

    If two tokens in one family could be live at once, a thief and the
    legitimate client would each hold a valid one and neither presentation would
    look like a replay. Asserted against the shipped SQL because the invariant
    has to hold for every writer, including one nobody has written yet -- a check
    in the service would hold only for the callers that remembered it.
    """
    index = re.search(
        r"CREATE UNIQUE INDEX refresh_tokens_one_live_per_family\s*\n?\s*"
        r"ON app_private\.refresh_tokens \(family_id\) WHERE consumed_at IS NULL;",
        migration,
    )
    assert index, "the one-live-token-per-family index is gone or no longer partial"


def test_the_stored_value_is_shaped_like_a_digest_and_not_like_a_token(
    migration: str,
) -> None:
    """A row holding a raw token is refused at write time, not discovered later.

    Without the CHECK, storing the token itself would work perfectly: every
    lookup would match, every test would pass, and the database would be holding
    the credential it exists to avoid holding.
    """
    assert "token_hash  text        NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$')" in migration


def test_a_revocation_records_both_when_and_why(migration: str) -> None:
    """Half a revocation is refused, which the rig measured as 23514 both ways.

    A moment without a reason cannot say whether a session was logged out or
    replayed, and that distinction is the column's whole value.
    """
    assert "refresh_families_revocation_is_complete" in migration
    assert "CHECK ((revoked_at IS NULL) = (revoked_reason IS NULL))" in migration


def test_the_down_block_refuses_like_every_released_migration(migration: str) -> None:
    assert "AP900: released platform migrations are fix-forward only" in migration


def test_the_migration_is_registered_and_its_template_exists() -> None:
    from agentic_postgres import migrations as migration_module

    manifest = migration_module.load_manifest()
    entry = next((e for e in manifest["migrations"] if e["name"] == "refresh_session_plane"), None)
    assert entry, "0023 is not in the manifest"
    assert Path(MIGRATION).is_file()
    assert entry["version"] == "20260902120023"
    assert entry["placeholders"] == ["object_owner", "auth_service"]
