"""The claim contract (ADR 0078).

Every check in ``verify_claims`` exists because the locked PostgREST was measured
to *serve* the corresponding bad token. So these tests are not a general sense of
rigour applied to a JWT library -- each one names the row of the negative matrix
it stands in for, and a check whose row says PostgREST refuses it is deliberately
not duplicated here.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from agentic_postgres import jwt_claims
from agentic_postgres.jwt_claims import ClaimError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ISSUER = "https://alpha-db.example.com/api/app/auth"
AUDIENCE = "alpha-dev"
NOW = 1_786_000_000


def token(**overrides: Any) -> dict[str, Any]:
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "6fa459ea-ee8a-3ca4-894e-db77e160355e",
        "role": "apg_alpha_dev_authenticated",
        "scope": ["notes:read", "tasks:read"],
        "token_use": "access",
        "jti": "0198e5b1-0000-7000-8000-000000000001",
        "iat": NOW,
        "nbf": NOW,
        "exp": NOW + 300,
        "credential_version": 7,
        "authz_version": 3,
    }
    payload.update(overrides)
    return payload


def verify(payload: dict[str, Any], *, now: int = NOW) -> dict[str, Any]:
    return jwt_claims.verify_claims(payload, issuer=ISSUER, audience=AUDIENCE, now=now)


# ---------------------------------------------------------------------------
# The control: a good token passes, so every refusal below is about the change
# ---------------------------------------------------------------------------


def test_a_conforming_token_is_accepted() -> None:
    assert verify(token())["sub"] == "6fa459ea-ee8a-3ca4-894e-db77e160355e"


def test_the_required_set_is_the_twelve_the_adr_names() -> None:
    """Pinned, because the set is a contract and not an implementation detail."""
    assert jwt_claims.REQUIRED_CLAIMS == (
        "iss",
        "aud",
        "sub",
        "role",
        "scope",
        "token_use",
        "jti",
        "iat",
        "nbf",
        "exp",
        "credential_version",
        "authz_version",
    )


@pytest.mark.parametrize("claim", jwt_claims.REQUIRED_CLAIMS)
def test_every_required_claim_is_required(claim: str) -> None:
    payload = token()
    del payload[claim]
    with pytest.raises(ClaimError, match="missing required claims"):
        verify(payload)


# ---------------------------------------------------------------------------
# The rows PostgREST SERVES. Each of these is a 200 in the negative matrix.
# ---------------------------------------------------------------------------


def test_a_token_from_another_issuer_is_refused() -> None:
    """The sharpest row: PostgREST has no issuer setting and never checks iss."""
    with pytest.raises(ClaimError, match="another issuer"):
        verify(token(iss="https://evil.invalid/api/app/auth"))


def test_a_token_for_another_audience_is_refused() -> None:
    with pytest.raises(ClaimError, match="not for this audience"):
        verify(token(aud="beta-dev"))


def test_a_token_use_outside_the_vocabulary_is_refused() -> None:
    """PostgREST has no opinion about token_use; this is the only check there is."""
    with pytest.raises(ClaimError, match="token_use"):
        verify(token(token_use="refresh"))  # noqa: S106 -- a discriminator value


def test_scope_must_be_an_array_not_a_delimited_string() -> None:
    """Measured: PostgREST serves `"notes:read tasks:read"` exactly as happily."""
    with pytest.raises(ClaimError, match="array of strings"):
        verify(token(scope="notes:read tasks:read"))


def test_scope_must_be_sorted_and_deduplicated() -> None:
    """The issuer sorts before signing, so an unsorted array did not come from it."""
    with pytest.raises(ClaimError, match="not sorted"):
        verify(token(scope=["tasks:read", "notes:read"]))
    with pytest.raises(ClaimError, match="repeats"):
        verify(token(scope=["notes:read", "notes:read"]))


def test_a_version_claim_must_be_a_non_negative_integer() -> None:
    for value in ("7", 7.0, None, -1):
        with pytest.raises(ClaimError):
            verify(token(credential_version=value))


def test_a_boolean_is_not_an_integer_version() -> None:
    """`True == 1` in Python, so a bool would compare equal for this claim's life."""
    with pytest.raises(ClaimError, match="not an integer"):
        verify(token(authz_version=True))


# ---------------------------------------------------------------------------
# The leeway, which is a measured product fact
# ---------------------------------------------------------------------------


def test_the_leeway_matches_what_postgrest_was_measured_to_apply() -> None:
    """30 seconds, bisected against the locked digest: 30 served, 31 refused.

    A verifier stricter than the one downstream would refuse tokens the
    deployment still honours and report it as an auth failure, which sends the
    reader to the wrong system.
    """
    assert jwt_claims.CLOCK_SKEW_SECONDS == 30


def test_expiry_is_honoured_with_the_leeway_and_not_beyond_it() -> None:
    payload = token()
    assert verify(payload, now=payload["exp"] + 29)
    with pytest.raises(ClaimError, match="expired"):
        verify(payload, now=payload["exp"] + 30)


def test_not_before_is_honoured_with_the_leeway_and_not_beyond_it() -> None:
    payload = token(nbf=NOW + 100, iat=NOW, exp=NOW + 400)
    assert verify(payload, now=NOW + 70)
    with pytest.raises(ClaimError, match="not yet valid"):
        verify(payload, now=NOW + 69)


def test_a_lifetime_beyond_the_ceiling_is_refused() -> None:
    ceiling = jwt_claims.MAX_TTL_SECONDS
    assert verify(token(exp=NOW + ceiling))
    with pytest.raises(ClaimError, match="lifetime exceeds"):
        verify(token(exp=NOW + ceiling + 1))


def test_a_token_that_expires_before_it_was_issued_is_refused() -> None:
    with pytest.raises(ClaimError, match="no later than it was issued"):
        verify(token(iat=NOW + 10, exp=NOW + 10, nbf=NOW))


# ---------------------------------------------------------------------------
# One authority for the shape
# ---------------------------------------------------------------------------


def test_the_sql_literal_lists_exactly_the_required_claims_in_order() -> None:
    """The hook's half is rendered from here; two lists is D177's defect."""
    literal = jwt_claims.sql_required_claims()
    assert literal.startswith("ARRAY[") and literal.endswith("]::text[]")
    names = [
        item.strip().strip("'") for item in literal[len("ARRAY[") : -len("]::text[]")].split(",")
    ]
    assert tuple(names) == jwt_claims.REQUIRED_CLAIMS


def test_a_claim_name_needing_escapes_fails_rather_than_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The literal is built by concatenation, so the guard is the quoting policy."""
    monkeypatch.setattr(jwt_claims, "REQUIRED_CLAIMS", ("iss", "not' ok"))
    with pytest.raises(ClaimError, match="bare identifier"):
        jwt_claims.sql_required_claims()


def test_the_enforcement_split_is_data_and_covers_the_contract() -> None:
    """`POSTGREST_ENFORCES` / `VERIFIED_ELSEWHERE` record a measurement.

    Kept as data rather than prose so that a later PostgREST which starts
    checking `iss` is compared against a value rather than a paragraph.
    """
    assert "iss" in jwt_claims.VERIFIED_ELSEWHERE
    assert "not checked at all" in jwt_claims.VERIFIED_ELSEWHERE["iss"]
    assert "aud_absent" in jwt_claims.VERIFIED_ELSEWHERE
    for claim in ("signature", "exp", "nbf", "aud", "kid", "role"):
        assert claim in jwt_claims.POSTGREST_ENFORCES
    overlap = set(jwt_claims.POSTGREST_ENFORCES) & set(jwt_claims.VERIFIED_ELSEWHERE)
    assert overlap == {"aud"} or not overlap, (
        "a claim in both tables is a claim whose row nobody decided; `aud` is the "
        "deliberate exception because PostgREST checks it only when present"
    )


def test_a_payload_that_is_not_an_object_is_refused() -> None:
    for payload in ([], "a string", None, 7):
        with pytest.raises(ClaimError):
            verify(payload)  # type: ignore[arg-type]


def test_verify_does_not_mutate_what_it_was_given() -> None:
    payload = token()
    before = copy.deepcopy(payload)
    verify(payload)
    assert payload == before
