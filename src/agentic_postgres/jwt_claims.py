"""The claim contract, and which verifier enforces which part of it.

**There was no contract before this** (D219). A bootstrap token carried `role`,
`iat`, `exp`, `iss`, `aud`, and `sub` for non-documentation roles; the
pre-request hook read `sub` and nothing else. No `scope`, `token_use`, `jti` or
`nbf` had ever been signed, published or verified. So this module is the first
one, written rather than extended, and ADR 0078 is its decision record.

**One authority for the shape.** Two verifiers read a token -- the auth service
with PyJWT, and the database's pre-request hook -- and a contract spelled twice
is a contract that drifts. D177 watched exactly that happen to a URL, where the
copy carrying a comment saying it was kept in step was the one that had drifted.
Everything either verifier needs to know about the shape is here, and the SQL
half is rendered from :func:`sql_required_claims` rather than typed into a
migration.

**What PostgREST enforces was measured, not read.** Against the locked digest
`postgrest:v14.16`, configured as `compose.yaml` configures it -- which matters,
because the first pass of that measurement left `PGRST_JWT_AUD` unset and
therefore reported a rig nobody deploys (ADR 0065). Every row in
:data:`POSTGREST_ENFORCES` and :data:`VERIFIED_ELSEWHERE` is an observed HTTP
status with a control in the same run.

The division is not tidy, and the two rows that matter are these:

* **`iss` is not checked at all.** PostgREST has no issuer setting. A token
  signed by the right key with any issuer whatsoever is served.
* **`aud` is checked only when it is present.** With `PGRST_JWT_AUD` set, a
  token carrying the wrong audience is refused -- and a token carrying *no*
  audience is served.

Both are why the hook is a verifier rather than a consumer.
"""

from __future__ import annotations

from typing import Any

from agentic_postgres.config import ManifestError

__all__ = [
    "CLOCK_SKEW_SECONDS",
    "MAX_TTL_SECONDS",
    "POSTGREST_ENFORCES",
    "REQUIRED_CLAIMS",
    "TOKEN_TYPE",
    "TOKEN_USES",
    "VERIFIED_ELSEWHERE",
    "ClaimError",
    "sql_required_claims",
    "verify_claims",
]


class ClaimError(ManifestError):
    """A token's claims do not satisfy the contract."""


#: The JOSE `typ`. Measured: PostgREST does **not** check it -- a token typed
#: `at+jwt` is served -- so this is enforced by the service and the hook or by
#: nobody.
TOKEN_TYPE = "JWT"  # noqa: S105 -- a JOSE header value, not a credential

#: The `token_use` discriminator. A token minted for one purpose must not be
#: accepted for another, and PostgREST has no opinion about this claim at all.
#: `agent` is issued in Session 6 and is refused at role switching until Session
#: 9 grants the memberships, which is a tested property rather than a side
#: effect.
TOKEN_USES = ("access", "agent")

#: Every claim a token must carry. Order is the wire order the issuer writes and
#: the order the SQL literal is rendered in, so a reviewer comparing the two
#: reads one list twice rather than two lists once.
REQUIRED_CLAIMS = (
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

#: Measured against the locked PostgREST, with a bisect: a token is accepted up
#: to **30 seconds** past `exp`, and up to 30 seconds before `nbf`. 30 is served
#: and 31 is refused, in both directions.
#:
#: This is not a curiosity. `jwt_keys.begin_rotation` computes a retirement
#: deadline as `max_token_ttl + clock_skew`, so a rotation that used a smaller
#: skew than the verifier applies would retire a key while tokens it signed were
#: still being served. Anything computing a rotation window reads this.
CLOCK_SKEW_SECONDS = 30

#: The ceiling on a token's lifetime, matching `bin/dev-token.py`. A token is
#: live for at most `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`, and that sum -- not
#: the TTL -- is the blast radius of a compromised token or a key cutover.
MAX_TTL_SECONDS = 900

#: What the locked PostgREST refuses on its own. Each entry is an observed 401
#: or 403 with the baseline served in the same run.
POSTGREST_ENFORCES = {
    "signature": "a token signed by another key, by `alg: none`, or by HS256 is refused (401)",
    "exp": f"refused more than {CLOCK_SKEW_SECONDS}s past expiry (PGRST303 'JWT expired')",
    "nbf": f"refused more than {CLOCK_SKEW_SECONDS}s before validity (PGRST303 'not yet valid')",
    "aud": "refused when PRESENT and not the configured audience (PGRST303 'not in audience')",
    "kid": "refused when present and matching no published key (PGRST301)",
    "role": "refused at SET ROLE when the authenticator holds no membership (403, SQLSTATE 42501)",
}

#: What PostgREST delivers without inspecting. Every one of these was served
#: with a 200 in the negative matrix, so each is verified by the auth service and
#: by the pre-request hook or it is verified by nothing.
VERIFIED_ELSEWHERE = {
    "iss": "not checked at all; PostgREST has no issuer setting",
    "aud_absent": "a token carrying NO audience is served even with PGRST_JWT_AUD set",
    "typ": "a header typed anything at all is served",
    "kid_absent": "a token with no kid is served; the key is resolved without it",
    "token_use": "delivered verbatim; PostgREST has no opinion",
    "scope": "delivered verbatim, as a JSON array, unparsed and uninterpreted",
    "credential_version": "delivered verbatim",
    "authz_version": "delivered verbatim",
}


def sql_required_claims() -> str:
    """The required claim names as a SQL ``text[]`` literal.

    The migration that carries the hook renders this rather than restating the
    list, so the database's idea of the contract cannot drift from the issuer's.
    Quoting is trivial and stays trivial: every name is matched against a
    conservative pattern first, so a claim name that needed escaping would fail
    here rather than produce a plausible literal.
    """
    for claim in REQUIRED_CLAIMS:
        if not claim.replace("_", "").isalnum() or not claim[0].isalpha():
            raise ClaimError(
                f"claim name {claim!r} is not a bare identifier. The SQL literal is "
                "rendered by concatenation and a name needing escapes would be a "
                "quoting decision made in the wrong place"
            )
    return "ARRAY[" + ", ".join(f"'{claim}'" for claim in REQUIRED_CLAIMS) + "]::text[]"


def verify_claims(
    payload: Any,
    *,
    issuer: str,
    audience: str,
    now: int,
    skew: int = CLOCK_SKEW_SECONDS,
) -> dict[str, Any]:
    """The service's half of the contract, as a pure function.

    Signature verification is not here and deliberately: that is PyJWT's, over
    key material this function never sees. What is here is everything a valid
    signature does *not* establish -- and PostgREST's negative matrix is the
    reason each check exists rather than a general sense of rigour.

    `skew` is a parameter rather than a constant read inside, so a test can pin
    the boundary without moving the product's value.
    """
    if not isinstance(payload, dict):
        raise ClaimError("the token payload is not a JSON object")

    missing = [claim for claim in REQUIRED_CLAIMS if claim not in payload]
    if missing:
        raise ClaimError(f"the token is missing required claims: {missing}")

    # `iss` first, because it is the one PostgREST does not check at all and the
    # one a token from anywhere else would fail.
    if payload["iss"] != issuer:
        raise ClaimError("the token was issued by another issuer")

    # Present AND correct. PostgREST refuses a wrong audience and serves an
    # absent one, so "present" is the half that has to be checked here.
    if payload["aud"] != audience:
        raise ClaimError("the token is not for this audience")

    if payload["token_use"] not in TOKEN_USES:
        raise ClaimError(f"token_use is not one of {TOKEN_USES}")

    for name in ("iat", "nbf", "exp", "credential_version", "authz_version"):
        value = payload[name]
        # `bool` is an `int` in Python, and `True` where a version is expected
        # would compare equal to 1 for the rest of this function's life.
        if not isinstance(value, int) or isinstance(value, bool):
            raise ClaimError(f"{name} is not an integer")

    if payload["credential_version"] < 0 or payload["authz_version"] < 0:
        raise ClaimError("a version claim is negative")

    if now + skew < payload["nbf"]:
        raise ClaimError("the token is not yet valid")
    if now - skew >= payload["exp"]:
        raise ClaimError("the token has expired")
    if payload["exp"] <= payload["iat"]:
        raise ClaimError("the token expires no later than it was issued")
    if payload["exp"] - payload["iat"] > MAX_TTL_SECONDS:
        raise ClaimError(f"the token's lifetime exceeds {MAX_TTL_SECONDS}s")

    scope = payload["scope"]
    if not isinstance(scope, list) or not all(isinstance(item, str) for item in scope):
        raise ClaimError(
            "scope is not an array of strings. PostgREST delivers whatever was signed, "
            "including a space-delimited string, so the shape is this verifier's to assert"
        )
    if sorted(scope) != list(scope):
        raise ClaimError("scope is not sorted; the issuer sorts before signing")
    if len(set(scope)) != len(scope):
        raise ClaimError("scope repeats an entry")

    for name in ("sub", "role", "jti"):
        if not isinstance(payload[name], str) or not payload[name]:
            raise ClaimError(f"{name} is not a non-empty string")

    return dict(payload)
