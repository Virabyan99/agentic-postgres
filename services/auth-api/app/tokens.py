"""The compact-JWT pre-parser, and key resolution that cannot reach a network.

**Why a pre-parser exists at all.** Measured in Run 7 against the locked
PyJWT 2.13.0:

* `jwt.get_unverified_header` accepted a token whose header was 5.3 MB of
  base64 and returned the parsed object. It bounds nothing.
* `jwt.decode` on that same 5.3 MB token base64-decoded it, JSON-parsed it and
  got as far as *signature verification* -- 32 ms of work, per request, before
  concluding the token was rubbish.
* A five-segment token (the JWE shape) failed with `DecodeError: Invalid header
  padding`, not with anything about segment count. The message sends the reader
  to the wrong problem.

So the bound is here, before PyJWT sees the string, and it is measured in bytes
and segments rather than inferred from a successful parse.

**Why key resolution is local only.** `jwt.PyJWKClient` takes a URI and fetches
over the network, with its own cache and its own timeout. This service must
never hold one: a verifier that can fetch its keys is a verifier whose trust
anchor is whatever answered the request, and the rotation design (prepare ->
acknowledge -> promote -> retire) depends on knowing exactly which key material
each verifier holds at each moment. `PyJWKSet.from_json` is the local path.
`test_the_service_never_constructs_a_network_jwks_client` asserts the absence
from source, because an import that is never called today is an import somebody
calls next session.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app import claims as _claims
from app.strict_json import MalformedBody, parse_object

#: The largest bearer token this service will look at, in bytes. A token issued
#: by this service carries twelve short claims and an RS256 signature: roughly
#: 700 bytes at 2048 bits, and under 1 KiB with any plausible scope list. 8 KiB
#: is an order of magnitude of headroom and still two hundred times smaller
#: than the 5.3 MB PyJWT was measured processing.
MAX_TOKEN_BYTES: Final = 8 * 1024

#: The largest JOSE header this service will parse, in bytes *before* base64
#: decoding. The header carries three members; 1 KiB is generous.
MAX_HEADER_BYTES: Final = 1024

#: A compact JWS has exactly three segments. Five is a JWE, which this service
#: does not accept in any form, and two is a truncation. Stated as a number
#: because PyJWT's own message for the five-segment case does not mention it.
COMPACT_SEGMENTS: Final = 3

#: The only signature algorithm. RS256, because ADR 0051 chose RSA and Session
#: 5 measured PostgREST accepting it; EdDSA is recorded as unmeasured (a
#: standing open item) and is therefore not in this set. A set rather than a
#: string so that adding a second one is a visible diff.
PERMITTED_ALGORITHMS: Final = frozenset({"RS256"})

#: The JOSE header members this service will accept. `alg` and `kid` are
#: required; `typ` is required and checked. Anything else -- `jku`, `jwk`,
#: `x5u`, `x5c`, `crit` -- is refused, and the first three of those are refused
#: precisely because they are instructions to go and fetch a key.
PERMITTED_HEADER_MEMBERS: Final = frozenset({"alg", "kid", "typ"})

#: The `typ` this service issues and accepts -- **read from the claim contract,
#: not chosen here** (D264).
#:
#: Run 7 wrote `at+jwt` at this line on RFC 9068's authority, and ADR 0078 had
#: already chosen `JWT` eight runs earlier. Two authorities for one header field
#: inside one service, in one session, which is §6's pattern arriving in the
#: code written to defend against it. The accepted ADR is the one that stays;
#: changing the value is a decision with alternatives and would need its own.
#:
#: RFC 9068's argument is real and is not dismissed: a distinct media type stops
#: a token minted for one purpose being replayed into a context expecting
#: another. What does that work here is `token_use`, which the contract already
#: requires and which `verify_claims` checks -- and which, unlike `typ`, is
#: signed inside the payload rather than in a header PostgREST ignores entirely.
TOKEN_TYPE: Final = _claims.TOKEN_TYPE


class MalformedToken(ValueError):
    """A token refused before any signature was checked.

    Every refusal in this module raises this one type. The caller turns it into
    a single generic response: which of nine structural problems a token had is
    information the holder of a bad token does not need.
    """


@dataclass(frozen=True, slots=True)
class PreParsed:
    """What the pre-parser is willing to say about a token it has not verified.

    Deliberately not the claims. The payload is still unverified at this point,
    and a structure carrying it would be a structure somebody reads a `sub` out
    of. What comes out is the header -- which is all that is needed to *choose a
    key* -- and the original token, to be handed to PyJWT intact.
    """

    token: str
    algorithm: str
    key_id: str
    typ: str


def pre_parse(token: str) -> PreParsed:
    """Bound and shape-check a compact JWS. Never verifies anything.

    Raises `MalformedToken`. Returns the header fields needed to select a
    verification key, and nothing from the payload.
    """
    if not isinstance(token, str):
        raise MalformedToken("a bearer token is text")

    # Length in bytes, not characters: the bound is on what has to be held.
    encoded = token.encode("ascii", errors="ignore")
    if len(encoded) != len(token):
        raise MalformedToken("a compact JWS is ASCII")
    if not token:
        raise MalformedToken("empty token")
    if len(encoded) > MAX_TOKEN_BYTES:
        raise MalformedToken(f"token exceeds {MAX_TOKEN_BYTES} bytes")

    segments = token.split(".")
    if len(segments) != COMPACT_SEGMENTS:
        raise MalformedToken(
            f"a compact JWS has {COMPACT_SEGMENTS} segments, this has {len(segments)}"
        )
    if not all(segments):
        raise MalformedToken("a compact JWS has no empty segment")

    header_segment = segments[0]
    if len(header_segment) > MAX_HEADER_BYTES:
        raise MalformedToken(f"JOSE header exceeds {MAX_HEADER_BYTES} bytes")

    header = _decode_header(header_segment)

    unknown = set(header) - PERMITTED_HEADER_MEMBERS
    if unknown:
        # Sorted so the message is stable; the message is for the log.
        raise MalformedToken(f"unapproved JOSE header members: {sorted(unknown)}")

    for member in ("alg", "kid", "typ"):
        if member not in header:
            raise MalformedToken(f"JOSE header has no {member!r}")
        if not isinstance(header[member], str):
            raise MalformedToken(f"JOSE header {member!r} is not a string")

    if header["alg"] not in PERMITTED_ALGORITHMS:
        raise MalformedToken(f"unpermitted algorithm: {header['alg']!r}")
    if header["typ"] != TOKEN_TYPE:
        raise MalformedToken(f"unpermitted token type: {header['typ']!r}")

    return PreParsed(
        token=token,
        algorithm=header["alg"],
        key_id=header["kid"],
        typ=header["typ"],
    )


def _decode_header(segment: str) -> dict[str, Any]:
    """base64url-decode and JSON-parse a JOSE header, strictly.

    Uses `strict_json.parse_object`, so a header carrying a duplicate member is
    refused here for the same reason a request body is: two `alg` values, one
    read by the key selector and one by a log line.
    """
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + padding)
    except (ValueError, TypeError) as exc:
        raise MalformedToken(f"JOSE header is not base64url: {exc}") from exc

    try:
        return parse_object(raw)
    except MalformedBody as exc:
        raise MalformedToken(f"JOSE header: {exc}") from exc


@dataclass(frozen=True, slots=True)
class LocalKeySet:
    """Verification keys read from a file this deployment wrote.

    Holds public material only, and says so in a way that is checkable: `load`
    refuses a JWKS containing any private RSA parameter. That check is not
    theatre -- the rotation design has a *private* JWK on the root plane and a
    published JWKS derived from it, and the failure this guards against is the
    two being wired the wrong way round, which would put a signing key into a
    file that is world-readable by design (ADR 0051).
    """

    keys: dict[str, dict[str, Any]]

    #: RFC 7517's private RSA members. `d` alone is the private exponent and is
    #: sufficient; the rest are the CRT parameters, listed so that a partially
    #: private key is caught too.
    PRIVATE_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth"})

    @classmethod
    def load(cls, raw: bytes | str) -> LocalKeySet:
        """Parse a JWKS document. Raises `MalformedToken` on anything unusable."""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        try:
            document = parse_object(raw)
        except MalformedBody as exc:
            raise MalformedToken(f"JWKS: {exc}") from exc

        entries = document.get("keys")
        if not isinstance(entries, list) or not entries:
            raise MalformedToken("JWKS has no 'keys' array")

        keys: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise MalformedToken("a JWKS key is an object")
            private = cls.PRIVATE_MEMBERS & set(entry)
            if private:
                raise MalformedToken(f"JWKS carries private key material: {sorted(private)}")
            key_id = entry.get("kid")
            if not isinstance(key_id, str) or not key_id:
                raise MalformedToken("a JWKS key has no 'kid'")
            if entry.get("kty") != "RSA":
                raise MalformedToken(f"unsupported key type: {entry.get('kty')!r}")
            algorithm = entry.get("alg")
            if algorithm not in PERMITTED_ALGORITHMS:
                raise MalformedToken(f"unpermitted key algorithm: {algorithm!r}")
            if key_id in keys:
                raise MalformedToken(f"duplicate kid in JWKS: {key_id!r}")
            keys[key_id] = entry

        return cls(keys=keys)

    @classmethod
    def from_path(cls, path: Path | str) -> LocalKeySet:
        """Read a JWKS from a file. The only way this service obtains keys."""
        return cls.load(Path(path).read_bytes())

    def resolve(self, pre_parsed: PreParsed) -> dict[str, Any]:
        """The key this token names, or a refusal. Never a fallback.

        A token whose `kid` is not in the set is refused rather than tried
        against every key. Trying them all is how a retired key keeps verifying
        tokens for as long as it is still published -- which is exactly the
        window the retire step exists to close.
        """
        key = self.keys.get(pre_parsed.key_id)
        if key is None:
            raise MalformedToken(f"no key with kid {pre_parsed.key_id!r}")
        return key

    def as_document(self) -> str:
        """The JWKS as it would be published. Public material by construction."""
        return json.dumps({"keys": list(self.keys.values())}, sort_keys=True)
