"""The claim contract, and which verifier enforces which part of it.

**There was no contract before this** (D219). A bootstrap token carried `role`,
`iat`, `exp`, `iss`, `aud`, and `sub` for non-documentation roles; the
pre-request hook read `sub` and nothing else. No `scope`, `token_use`, `jti` or
`nbf` had ever been signed, published or verified. So this module is the first
one, written rather than extended, and ADR 0078 is its decision record.

**One authority for the shape, and since Run 8 it is not this file** (ADR 0084).
`REQUIRED_CLAIMS`, the token uses, the skew, the TTL ceiling and `verify_claims`
live in `services/auth-api/app/claims.py` -- inside the image's build context --
and are re-exported here. The service and the repository then read one
declaration rather than two, which is what D177 cost the last time a contract
was spelled twice: the copy carrying a comment saying it was kept in step was
the one that had drifted.

What remains here is everything that is *about* the contract rather than part of
it, and neither half is something the running service does:

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

from agentic_postgres import service_source

_claims = service_source.load("claims")

#: Re-exported from the service's build context. Assigned rather than imported
#: with a `from` so that a reader sees where they come from.
ClaimError = _claims.ClaimError
REQUIRED_CLAIMS = _claims.REQUIRED_CLAIMS
TOKEN_TYPE = _claims.TOKEN_TYPE
TOKEN_USES = _claims.TOKEN_USES
CLOCK_SKEW_SECONDS = _claims.CLOCK_SKEW_SECONDS
MAX_TTL_SECONDS = _claims.MAX_TTL_SECONDS
verify_claims = _claims.verify_claims

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

    Stays in this module rather than moving with the contract: rendering a
    migration literal is something the repository does and the service does not.
    """
    for claim in REQUIRED_CLAIMS:
        if not claim.replace("_", "").isalnum() or not claim[0].isalpha():
            raise ClaimError(
                f"claim name {claim!r} is not a bare identifier. The SQL literal is "
                "rendered by concatenation and a name needing escapes would be a "
                "quoting decision made in the wrong place"
            )
    return "ARRAY[" + ", ".join(f"'{claim}'" for claim in REQUIRED_CLAIMS) + "]::text[]"
