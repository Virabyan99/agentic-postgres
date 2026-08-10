"""The bootstrap issuer's public half: JWKs, thumbprints, and a rotation window.

ADR 0051 decided the shape and ADR 0055 decided the storage. What is here is
everything about that key that can be computed without holding it: a public JWK
from a modulus and an exponent, an RFC 7638 thumbprint, a verification-only JWKS
that refuses private material, and the two-phase rotation state machine with the
deadline the deployed document records.

**Nothing here reads the private key and nothing here signs.** The private key is
a PEM that only `openssl` handles (ADR 0055), and the modulus and exponent this
module builds a JWK from are read out of `openssl rsa -noout -modulus -text` by
the caller. That split is what makes every rule below testable with no key, no
host and no container -- which matters, because the rules are the security
properties.

Three of them are worth naming here rather than leaving in a docstring below:

* **A public JWK carrying `d` is a private key with a misleading label.** The
  refusal is by parameter name against the complete RFC 7518 set, and it is
  asserted against a deliberately malformed input rather than trusted.
* **`kid` is derived, not chosen.** RFC 7638 makes it a function of the key, so
  two keys cannot share one and one key cannot have two. A supplied `kid` that
  disagrees with the thumbprint is refused rather than preferred.
* **A rotation has a deadline and the deadline is a value.** Phase one publishes
  two verification keys and switches signing; phase two removes the retiring key
  and may not run early. "After the tokens have expired" as a sentence is a
  rotation that never completes; as `retire_after` it is a comparison.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

#: Every private RSA parameter RFC 7518 defines. A public JWK carrying any of
#: them is not a public JWK. `oth` is in the list although it appears only in
#: multi-prime keys, because "we do not generate those" is a statement about the
#: generator and this is a check on an input.
PRIVATE_JWK_PARAMETERS = ("d", "p", "q", "dp", "dq", "qi", "oth")

#: The members an RSA public JWK carries here, and the exact set. `alg` and `use`
#: are pinned rather than optional so that a verifier reading this document
#: cannot be talked into a different algorithm by the document itself.
PUBLIC_JWK_MEMBERS = frozenset({"kty", "n", "e", "alg", "use", "kid"})

#: RS256 and only RS256 (ADR 0051). Asymmetric, so a verifier holds nothing that
#: can sign; and the one algorithm every JWT implementation supports without
#: configuration, which matters for a key that exists to be verified elsewhere.
ALGORITHM = "RS256"

#: At most two keys verify at once: the active one, and during a rotation the one
#: retiring. Two is a ceiling rather than a convention because an unbounded
#: verification set is a set nobody ever retires from -- every key stays valid
#: because removing one is always something that can be done later.
MAX_VERIFICATION_KEYS = 2

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX = re.compile(r"^[0-9A-Fa-f]+$")

__all__ = [
    "ALGORITHM",
    "MAX_VERIFICATION_KEYS",
    "PRIVATE_JWK_PARAMETERS",
    "PUBLIC_JWK_MEMBERS",
    "JwkError",
    "base64url_decode",
    "base64url_encode",
    "begin_rotation",
    "build_jwks",
    "complete_rotation",
    "initial_key_state",
    "public_jwk",
    "thumbprint",
    "validate_key_state",
]


class JwkError(ValueError):
    """A key, a key set or a rotation is not usable as stated."""


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def base64url_encode(raw: bytes) -> str:
    """Unpadded base64url, which is the only spelling JOSE accepts.

    Padding is stripped rather than left optional. A `kid` that compares unequal
    to itself across two encoders is a rotation that silently never completes:
    the new key is published, the old one is never recognised as the old one, and
    the verification set grows instead of turning over.
    """
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    """The inverse, restoring the padding the encoder removed."""
    if not _BASE64URL.match(value):
        raise JwkError(f"not unpadded base64url: {value!r}")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _integer_to_base64url(value: int) -> str:
    """A JOSE `n` or `e`: the big-endian minimal-length unsigned encoding.

    Minimal length matters and is easy to get wrong. A leading zero byte changes
    the base64url string without changing the number, so two encoders that
    disagree about padding produce two thumbprints for one key -- and the
    thumbprint is the identifier.
    """
    if value <= 0:
        raise JwkError(f"a JWK integer parameter must be positive, got {value}")
    return base64url_encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))


# ---------------------------------------------------------------------------
# The public key
# ---------------------------------------------------------------------------


def public_jwk(*, modulus_hex: str, exponent: int) -> dict[str, str]:
    """An RSA public JWK from what `openssl` prints about a key.

    `openssl rsa -noout -modulus` emits `Modulus=` followed by uppercase hex, and
    `-text` names the exponent in decimal. Both are read by the caller and passed
    here, so this module never runs a subprocess and never touches a key file.

    The `kid` is computed, not accepted. That is the whole of RFC 7638's value:
    the identifier is a function of the key, so a rotation cannot publish a new
    key under the old key's name, and two projects cannot accidentally share one.
    """
    cleaned = modulus_hex.strip().removeprefix("Modulus=").strip()
    if not _HEX.match(cleaned):
        raise JwkError(
            f"not a hexadecimal modulus: {modulus_hex!r}. `openssl rsa -noout -modulus` "
            "prints `Modulus=` and uppercase hex; anything else means the key was not read"
        )
    modulus = int(cleaned, 16)
    if modulus.bit_length() < 2048:
        raise JwkError(
            f"the modulus is {modulus.bit_length()} bits, below 2048. A key this short is "
            "not refused because a verifier would reject it -- most will not -- but "
            "because nothing should be signing with it"
        )
    if exponent < 3 or exponent % 2 == 0:
        raise JwkError(f"not a usable RSA public exponent: {exponent}")

    jwk = {
        "kty": "RSA",
        "n": _integer_to_base64url(modulus),
        "e": _integer_to_base64url(exponent),
        "alg": ALGORITHM,
        "use": "sig",
    }
    return {**jwk, "kid": thumbprint(jwk)}


def thumbprint(jwk: dict[str, Any]) -> str:
    """The RFC 7638 thumbprint: base64url SHA-256 of the canonical member set.

    Canonical means exactly three members for an RSA key -- `e`, `kty`, `n` --
    in lexicographic order, with no whitespace. Everything else in the JWK,
    including `alg`, `use` and any `kid` already present, is excluded by the
    specification. Including one would make the identifier depend on metadata
    rather than on the key, which is the property being bought.
    """
    missing = {"kty", "n", "e"} - set(jwk)
    if missing:
        raise JwkError(f"cannot compute a thumbprint without {sorted(missing)}")
    if jwk["kty"] != "RSA":
        raise JwkError(f"only RSA keys are handled here, got {jwk['kty']!r}")

    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64url_encode(sha256(canonical.encode("utf-8")).digest())


def assert_public(jwk: dict[str, Any]) -> None:
    """Refuse a JWK carrying private material (ADR 0051).

    This is the check that stops a private key being published to a verifier by
    a mistake in a derivation nobody reads. It refuses by parameter name against
    the complete RFC 7518 set rather than by checking for the members a public
    key has, because the failure to catch is an *extra* member, and a check
    written the other way round passes on a superset.
    """
    present = [parameter for parameter in PRIVATE_JWK_PARAMETERS if parameter in jwk]
    if present:
        raise JwkError(
            f"this JWK carries the private parameters {present}. It is a signing key, and "
            "the set PostgREST receives is verification-only"
        )
    unexpected = set(jwk) - PUBLIC_JWK_MEMBERS
    if unexpected:
        raise JwkError(
            f"unexpected JWK members {sorted(unexpected)}. The published set carries "
            f"exactly {sorted(PUBLIC_JWK_MEMBERS)}; anything else is a member nobody "
            "decided to publish"
        )


def build_jwks(keys: list[dict[str, Any]]) -> dict[str, Any]:
    """The verification-only key set PostgREST is given.

    Every rule is applied to every key, and the order of the list is preserved:
    the active key is first by convention, and a set whose order changed between
    two renders would make a byte comparison of the rendered file meaningless.
    """
    if not keys:
        raise JwkError("a key set with no keys verifies nothing")
    if len(keys) > MAX_VERIFICATION_KEYS:
        raise JwkError(
            f"{len(keys)} verification keys, above the ceiling of {MAX_VERIFICATION_KEYS}. "
            "An unbounded set is a set nobody retires from"
        )

    seen: set[str] = set()
    for jwk in keys:
        assert_public(jwk)
        if jwk.get("alg") != ALGORITHM:
            raise JwkError(
                f"key {jwk.get('kid')!r} declares alg {jwk.get('alg')!r}; this issuer is "
                f"{ALGORITHM} and a verifier that accepts two algorithms accepts the "
                "weaker one"
            )
        computed = thumbprint(jwk)
        if jwk.get("kid") != computed:
            raise JwkError(
                f"kid {jwk.get('kid')!r} is not this key's RFC 7638 thumbprint "
                f"({computed}). A kid chosen beside the key rather than derived from it "
                "can name a key that is not present"
            )
        if computed in seen:
            raise JwkError(f"two keys share the kid {computed}; they are the same key")
        seen.add(computed)

    return {"keys": [dict(jwk) for jwk in keys]}


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


def initial_key_state(*, jwk: dict[str, Any], temporary: bool = True) -> dict[str, Any]:
    """The `jwt` block's key members for a project with one key and no rotation."""
    assert_public(jwk)
    return {
        "algorithm": ALGORITHM,
        "active_kid": jwk["kid"],
        "verification_kids": [jwk["kid"]],
        "temporary": temporary,
        "retire_after": None,
    }


def begin_rotation(
    state: dict[str, Any],
    *,
    incoming: dict[str, Any],
    now: datetime,
    max_token_ttl_seconds: int,
    clock_skew_seconds: int,
) -> dict[str, Any]:
    """Phase one: sign with the new key, verify with both, record the deadline.

    The deadline is `now + max_token_ttl + clock_skew`, which is the moment after
    which no token signed by the retiring key can still be inside its own
    lifetime. It is computed here rather than at phase two, because at phase two
    the moment the switch happened is exactly what nobody remembers.

    A rotation cannot begin while one is in flight. Two overlapping rotations
    would need three verification keys, and the third is the one that never gets
    removed.
    """
    validate_key_state(state)
    assert_public(incoming)

    if state["retire_after"] is not None:
        raise JwkError(
            f"a rotation is already in flight, due to complete after {state['retire_after']}. "
            "Beginning another would need a third verification key, and a third key is one "
            "nobody retires"
        )
    if incoming["kid"] == state["active_kid"]:
        raise JwkError(
            "the incoming key is the active key. Rotating to the same material publishes "
            "a new deadline for an unchanged key, which is a rotation nobody performed"
        )
    if max_token_ttl_seconds < 1 or clock_skew_seconds < 0:
        raise JwkError("the overlap window must be a positive token lifetime plus a skew")

    deadline = now.astimezone(UTC) + timedelta(seconds=max_token_ttl_seconds + clock_skew_seconds)
    return {
        **state,
        "active_kid": incoming["kid"],
        # The incoming key first: `build_jwks` preserves order, and the active
        # key leading the set is what makes a reader's first guess the right one.
        "verification_kids": [incoming["kid"], state["active_kid"]],
        "retire_after": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def complete_rotation(state: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Phase two: publish only the active key, and not before the deadline.

    Refusing early is the half that matters. Completing a rotation before the
    window closes invalidates tokens that are still inside their own lifetime,
    and the failure arrives at whoever holds one -- as an authentication error
    with no cause visible from where it is seen.
    """
    validate_key_state(state)
    if state["retire_after"] is None:
        raise JwkError("no rotation is in flight; there is nothing to complete")

    deadline = datetime.strptime(state["retire_after"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if now.astimezone(UTC) < deadline:
        raise JwkError(
            f"the overlap window closes at {state['retire_after']} and it is "
            f"{now.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}. Removing the retiring "
            "key now would refuse tokens that are still inside their own lifetime"
        )

    return {**state, "verification_kids": [state["active_kid"]], "retire_after": None}


def validate_key_state(state: dict[str, Any]) -> dict[str, Any]:
    """The invariants of the `jwt` block's key members, wherever it came from.

    Applied on the way in as well as on the way out, so a state read from a
    deployed document written by an older release is checked before it is used to
    decide anything.
    """
    required = {"algorithm", "active_kid", "verification_kids", "temporary", "retire_after"}
    missing = required - set(state)
    if missing:
        raise JwkError(f"the key state is missing {sorted(missing)}")

    if state["algorithm"] != ALGORITHM:
        raise JwkError(f"algorithm {state['algorithm']!r} is not {ALGORITHM}")

    kids = state["verification_kids"]
    if not isinstance(kids, list) or not kids:
        raise JwkError("verification_kids must be a non-empty list")
    if len(kids) > MAX_VERIFICATION_KEYS:
        raise JwkError(f"{len(kids)} verification kids, above {MAX_VERIFICATION_KEYS}")
    if len(set(kids)) != len(kids):
        raise JwkError(f"verification_kids repeats a key: {kids}")
    if state["active_kid"] not in kids:
        raise JwkError(
            f"active_kid {state['active_kid']!r} is not in verification_kids {kids}. Every "
            "token this issuer signs would be refused by every verifier reading this"
        )

    # The two halves of "a rotation is in flight" have to agree. One key with a
    # deadline is a rotation whose second phase would remove nothing; two keys
    # without one is an overlap that never ends.
    if (state["retire_after"] is None) != (len(kids) == 1):
        raise JwkError(
            f"retire_after is {state['retire_after']!r} beside {len(kids)} verification "
            "keys. A deadline and a second key are the same fact, and one without the "
            "other is a rotation that either removes nothing or never ends"
        )
    return state
