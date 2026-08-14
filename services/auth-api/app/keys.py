"""The signing key, the `kid` derived from it, and the JWKS published from it.

**Nothing here stores a public key.** ADR 0051's rule is that the verification
material is *derived* from the private key -- "one value, one derivation, and
nothing that can drift from the key it claims to describe" -- and D257 refused a
stored `jwt_public_jwks` secret for exactly that reason. This module is the
service's half of that derivation: a PEM in, a JWKS and a `kid` out.

**The `kid` is an RFC 7638 thumbprint**, and it is computed here as well as in
`agentic_postgres.jwt_keys`. That is two implementations, deliberately, and the
contract test that ties them is not a tautology: this one starts from a PEM and
`cryptography`'s integers, and the repository's starts from a hexadecimal
modulus read out of `openssl`. Two inputs, two code paths, one required answer.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.claims import TOKEN_TYPE
from app.tokens import PERMITTED_ALGORITHMS

#: The one signature algorithm. Read from `tokens` rather than restated: the
#: pre-parser refuses everything else, and a signer that could produce what the
#: verifier refuses would be a service that cannot read its own tokens.
ALGORITHM: Final = "RS256"

#: The smallest modulus this service will sign with. ADR 0051 chose 2048-bit
#: RSA; a key below that is a provider mistake, and it is worth failing the
#: start over rather than issuing tokens nobody can be told are weak.
MINIMUM_KEY_BITS: Final = 2048


class KeyMaterialError(RuntimeError):
    """The signing key is missing, unreadable, or not what this service signs with.

    Raised at startup, never per request. A service that discovered its key was
    unusable on the first login would report a credential problem for a
    deployment problem.
    """


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _integer_to_base64url(value: int) -> str:
    """RFC 7518 base64url of an unsigned big-endian integer, minimally encoded.

    `bit_length() + 7 // 8` rather than a fixed width: a leading zero byte is a
    different base64 string for the same number, and the thumbprint is a hash of
    the string.
    """
    if value < 0:
        raise KeyMaterialError("a JWK parameter is negative")
    width = max(1, (value.bit_length() + 7) // 8)
    return _base64url(value.to_bytes(width, "big"))


def thumbprint(jwk: dict[str, Any]) -> str:
    """RFC 7638: SHA-256 over the canonical JSON of the required members only.

    For RSA the required members are exactly `e`, `kty`, `n`, in lexicographic
    order, with no whitespace. Every other member -- `alg`, `use`, `kid` -- is
    excluded, which is what makes the thumbprint a property of the KEY rather
    than of the document describing it.
    """
    required = {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}
    canonical = json.dumps(required, separators=(",", ":"), sort_keys=True)
    return _base64url(hashlib.sha256(canonical.encode("utf-8")).digest())


@dataclass(frozen=True, slots=True)
class SigningKey:
    """A private key this service signs with, and the public half it publishes."""

    private_pem: bytes
    public_jwk: dict[str, Any]
    key_id: str

    def jwks(self) -> dict[str, Any]:
        """The document `/auth/jwks.json` serves. Public members only.

        Built from `public_jwk` rather than held alongside it, so there is no
        second copy that could be published after the key changed.
        """
        return {"keys": [dict(self.public_jwk)]}


def load_signing_key(path: Path | str) -> SigningKey:
    """Read a PKCS#8 PEM and derive everything else from it.

    Refuses anything that is not an RSA private key of at least
    `MINIMUM_KEY_BITS`. A public key here would be the rotation design wired
    backwards -- the prepared *private* half is root-plane and must reach no
    running process (D257) -- so the refusal names that rather than the parse.
    """
    raw = Path(path).read_bytes()
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError) as exc:
        raise KeyMaterialError(f"the signing key is not a readable PEM private key: {exc}") from exc

    if not isinstance(key, rsa.RSAPrivateKey):
        raise KeyMaterialError(
            f"the signing key is a {type(key).__name__}; ADR 0051 chose RSA and only "
            "RS256 is published"
        )
    if key.key_size < MINIMUM_KEY_BITS:
        raise KeyMaterialError(
            f"the signing key is {key.key_size} bits, below the {MINIMUM_KEY_BITS} "
            "ADR 0051 requires"
        )

    numbers = key.public_key().public_numbers()
    jwk: dict[str, Any] = {
        "kty": "RSA",
        "n": _integer_to_base64url(numbers.n),
        "e": _integer_to_base64url(numbers.e),
        "alg": ALGORITHM,
        "use": "sig",
    }
    jwk["kid"] = thumbprint(jwk)

    if ALGORITHM not in PERMITTED_ALGORITHMS:
        raise KeyMaterialError(
            f"{ALGORITHM} is not in the pre-parser's permitted set; the service would "
            "sign tokens it refuses to read"
        )

    return SigningKey(private_pem=raw, public_jwk=jwk, key_id=jwk["kid"])


def jose_header(key: SigningKey) -> dict[str, str]:
    """The header every token this service signs carries.

    `typ` comes from the claim contract, not from this module. Run 7 wrote
    `at+jwt` here on RFC 9068's authority while ADR 0078 had already chosen
    `JWT`, which is two authorities for one header field inside one service
    (D264). One of them had to go, and the accepted ADR is the one that stays.
    """
    return {"alg": ALGORITHM, "kid": key.key_id, "typ": TOKEN_TYPE}
