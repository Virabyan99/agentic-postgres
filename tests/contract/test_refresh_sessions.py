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

import dataclasses
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


# ---------------------------------------------------------------------------
# 0024: the callable surface, and the one overlap it declares (Run 3)
# ---------------------------------------------------------------------------

FUNCTIONS_MIGRATION = REPO_ROOT / "migrations" / "templates" / "0024-refresh-session-functions.sql"


@pytest.fixture(scope="module")
def functions() -> str:
    return FUNCTIONS_MIGRATION.read_text(encoding="utf-8")


def test_the_sql_guard_and_the_state_machine_refuse_on_the_same_three_facts(
    functions: str,
) -> None:
    """The one place the transition and its meaning overlap, made a checked
    correspondence instead of a second authority (ADR 0171).

    `auth_consume_refresh_token`'s UPDATE guards on three conditions and
    `classify` refuses on three facts, and they have to be the same three. The
    duplication is not removable: only consumption RACES, so only consumption
    needs the database -- but a guard that checked consumption alone would
    CONSUME an expired token before refusing it, and the next presentation of
    that token would read as a replay and revoke the family. **A false reuse
    alarm on a legitimate late retry is worse than the duplication.**

    So this asserts the correspondence rather than the wording, in the way
    `jwt_claims.sql_required_claims()` is asserted against 0011's literal. It
    goes red if a condition is dropped from the SQL, which is the change that
    would silently make one of `classify`'s outcomes unreachable.
    """
    guard = re.search(
        r"UPDATE app_private\.refresh_tokens t\s*\n\s*SET consumed_at.*?RETURNING",
        functions,
        re.DOTALL,
    )
    assert guard, "the consuming UPDATE is gone or no longer shaped as expected"
    body = guard.group(0)

    assert "t.consumed_at IS NULL" in body, "the guard no longer excludes a consumed token"
    assert "t.expires_at   > pg_catalog.now()" in body, (
        "the guard no longer excludes an expired one"
    )
    assert "f.revoked_at  IS NULL" in body, "the guard no longer excludes a revoked family"

    # And the state machine refuses on exactly those three, plus absence. The
    # fields of TokenState are the enumeration both sides have to agree on.
    fields = {f.name for f in dataclasses.fields(refresh_sessions.TokenState)}
    assert fields == {"found", "consumed", "family_revoked", "expires_at"}, (
        f"TokenState carries {sorted(fields)}; the SQL guard checks three conditions plus "
        "the row's existence, and a fourth fact here would be one the guard does not know"
    )


def test_the_function_revokes_the_family_where_it_detects_the_replay(functions: str) -> None:
    """Detection and response in one transaction, not two calls.

    A service that classified a replay, logged it, and died before issuing the
    revocation would have found a leaked chain and left it live. This is the one
    action the SQL takes on its own reading of a fact, and it is deliberate.
    """
    assert "revoked_reason = 'reuse_detected'" in functions
    revoke = re.search(
        r"UPDATE app_private\.refresh_families f\s*\n\s*SET revoked_at.*?f\.revoked_at   IS NULL;",
        functions,
        re.DOTALL,
    )
    assert revoke, "the reuse revocation is gone or no longer guarded"
    assert "t.consumed_at  IS NOT NULL" in revoke.group(0), (
        "the revocation no longer requires that the presented token was consumed, so it "
        "would end a family on any failed presentation"
    )


def test_listing_and_revoking_are_scoped_to_the_owner_in_sql(functions: str) -> None:
    """A caller cannot read or end another subject's session by naming its id.

    Both functions take `p_user_id` and filter on it. Passing the family id
    alone would make this an unauthenticated object reference, which is the
    shape ADR 0029 refuses everywhere else in this schema -- and a check in the
    service instead would hold only for the callers that remembered it.
    """
    for signature, filter_clause in [
        (
            r"CREATE FUNCTION app_private\.auth_list_sessions\(p_user_id uuid\)",
            "f.user_id = p_user_id",
        ),
        (r"CREATE FUNCTION app_private\.auth_revoke_session\(", "AND user_id = p_user_id"),
    ]:
        assert re.search(signature, functions), f"{signature} is gone"
        assert filter_clause in functions, f"{filter_clause!r} is not in 0024"


def test_the_service_is_granted_execute_and_no_table_privilege(functions: str) -> None:
    """The property is the ABSENCE, so it is asserted rather than assumed.

    `auth_service` holds EXECUTE on four functions and SELECT on neither table,
    which is what makes "the auth service cannot read a token digest it was not
    handed" a fact of the catalog rather than of the service's code.
    """
    # Whole statements, not lines: three of the five GRANTs wrap, and a
    # line-based reader silently saw two of them. A parser that misses part of
    # what it checks reports a smaller set as agreement.
    statements = re.findall(
        r"GRANT EXECUTE ON FUNCTION\s+(.*?)TO \{\{auth_service\}\};",
        functions,
        re.DOTALL,
    )
    granted = {
        name
        for statement in statements
        for name in re.findall(r"app_private\.(auth_\w+)\(", statement)
    }
    assert granted == {
        "auth_open_session",
        "auth_consume_refresh_token",
        "auth_list_sessions",
        "auth_revoke_session",
    }, f"the granted set moved: {sorted(granted)}"

    # `auth_revoke_user_sessions` is absent on purpose (D837). Ending every
    # session a subject has is what Run 5's password reset needs, and granting
    # EXECUTE on it before that caller exists is the grant 0011's rule -- and
    # this module's own test over 0023 -- refuses.
    # The CONSTRUCT, not the string. `not in functions` matched the comment that
    # explains the omission -- D464's family, fired by the sentence documenting
    # the decision it was checking.
    assert "CREATE FUNCTION app_private.auth_revoke_user_sessions" not in functions, (
        "a function arrived before its caller, one run after the test that forbids it"
    )
    assert "auth_revoke_user_sessions" not in " ".join(statements), (
        "auth_revoke_user_sessions is granted before Run 5's caller exists"
    )

    table_grants = [
        line.strip()
        for line in functions.splitlines()
        if line.strip().startswith("GRANT")
        and ("refresh_tokens" in line or "refresh_families" in line)
    ]
    assert not table_grants, f"0024 grants a table privilege: {table_grants}"


def test_every_session_function_is_security_definer_with_a_fixed_search_path(
    functions: str,
) -> None:
    """Five functions, five identical preambles.

    A SECURITY DEFINER function without `SET search_path` resolves unqualified
    names through the caller's path, which is how a definer function ends up
    running somebody else's `now()`. Asserted per function rather than counted,
    so a sixth added later without it fails here.
    """
    declared = re.findall(r"CREATE FUNCTION app_private\.(auth_\w+)\(", functions)
    assert len(declared) == 4, f"expected four functions, found {declared}"

    blocks = functions.split("CREATE FUNCTION app_private.")[1:]
    for block in blocks:
        name = block.split("(")[0]
        assert "SECURITY DEFINER" in block, f"{name} is not SECURITY DEFINER"
        assert "SET search_path = pg_catalog, pg_temp" in block, f"{name} has no fixed search_path"


def test_the_functions_migration_is_registered_and_follows_the_tables() -> None:
    from agentic_postgres import migrations as migration_module

    manifest = migration_module.load_manifest()
    names = [entry["name"] for entry in manifest["migrations"]]
    assert "refresh_session_functions" in names
    assert names.index("refresh_session_plane") < names.index("refresh_session_functions"), (
        "the functions would be created before the tables they read"
    )
