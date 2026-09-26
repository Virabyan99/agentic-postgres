"""The claim contract's shape, and the service's half of verifying it.

**This module is the authority and `agentic_postgres.jwt_claims` imports it**
(ADR 0084). Both the issuer and the repository need the same claim names, the
same TTL ceiling and the same skew; a contract spelled twice is a contract that
drifts, and D177 watched exactly that happen to a URL where the copy carrying a
comment saying it was kept in step was the one that had drifted.

What stayed in `agentic_postgres.jwt_claims` is everything that is *about* this
contract rather than part of it: `POSTGREST_ENFORCES` and `VERIFIED_ELSEWHERE`
are the record of a measurement against the locked PostgREST, and
`sql_required_claims` renders a migration literal. Neither is something the
running service does.

Standard library only, which is what makes the import safe from a deploy host
with none of the service's dependencies installed.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

__all__ = [
    "APPROVAL_CLAIM",
    "CLOCK_SKEW_SECONDS",
    "MAX_TTL_SECONDS",
    "REQUIRED_CLAIMS",
    "TOKEN_TYPE",
    "TOKEN_USES",
    "ClaimError",
    "approval_claim",
    "verify_claims",
]


class ClaimError(ValueError):
    """A token's claims do not satisfy the contract.

    `ValueError` rather than the repository's `ManifestError`: this module may
    not import `agentic_postgres.config`, and a token is not a manifest.
    `agentic_postgres.jwt_claims` re-exports this exact class, so
    `pytest.raises(jwt_claims.ClaimError)` and `except ClaimError` inside the
    service catch the same object.
    """


#: The JOSE `typ`. Measured: PostgREST does **not** check it -- a token typed
#: `at+jwt` is served -- so this is enforced by the service and the hook or by
#: nobody.
TOKEN_TYPE = "JWT"  # noqa: S105 -- a JOSE header value, not a credential

#: The `token_use` discriminator. A token minted for one purpose must not be
#: accepted for another, and PostgREST has no opinion about this claim at all.
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
CLOCK_SKEW_SECONDS = 30

#: The ceiling on a token's lifetime. A token is live for at most
#: `MAX_TTL_SECONDS + CLOCK_SKEW_SECONDS`, and that sum -- not the TTL -- is the
#: blast radius of a compromised token or a key cutover.
MAX_TTL_SECONDS = 900

#: A human's approval of ONE write, carried by ONE workflow step token (ADR
#: 0231). **Optional, and deliberately not in `REQUIRED_CLAIMS`**: a token
#: without it is every token there has ever been, and the database's literal of
#: required claims does not move. Only `AuthService.step_token` mints it, and
#: only from a decided row it reads itself; the plane serves a
#: `requires_approval` write only when its `tool` and `key` name the call being
#: made. Rig 33a measured that an extra claim passes this verifier, the plane's,
#: PostgREST and the pre-request hook.
APPROVAL_CLAIM = "apg_approval"

#: The idempotency key's own shape (ADR 0181), which is what the claim's `key`
#: must be to name one.
_KEY = re.compile(r"^[\x21-\x7e]{8,255}$")


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


def approval_claim(payload: Any) -> dict[str, str] | None:
    """The token's approval, or `None` when it carries none.

    A pure shape check over claims ALREADY verified: exactly `id` (a uuid),
    `tool` and `key` (non-empty strings, the key in the idempotency key's own
    shape). Anything else present under the name is a `ClaimError`, never a
    `None` -- a malformed approval is not the absence of one, and the caller
    turns it into the ordinary approval refusal rather than serving or
    crashing.
    """
    if not isinstance(payload, dict) or APPROVAL_CLAIM not in payload:
        return None
    claim = payload[APPROVAL_CLAIM]
    if not isinstance(claim, dict) or set(claim) != {"id", "tool", "key"}:
        raise ClaimError(f"{APPROVAL_CLAIM} is not an object of exactly id, tool and key")
    for name in ("id", "tool", "key"):
        if not isinstance(claim[name], str) or not claim[name]:
            raise ClaimError(f"{APPROVAL_CLAIM}.{name} is not a non-empty string")
    try:
        uuid.UUID(claim["id"])
    except ValueError as error:
        raise ClaimError(f"{APPROVAL_CLAIM}.id is not a uuid") from error
    if not _KEY.fullmatch(claim["key"]):
        raise ClaimError(f"{APPROVAL_CLAIM}.key is not an idempotency key")
    return {"id": claim["id"], "tool": claim["tool"], "key": claim["key"]}
