"""The bounded pre-parser and local-only key resolution.

`API-AUTH-002` and `SEC-KEY-001`, the halves that run offline.

Every bound here has a companion assertion showing what PyJWT does without it,
because a bound whose necessity is asserted rather than shown is a bound
somebody removes as redundant. Measured in Run 7 against the locked PyJWT
2.13.0.
"""

from __future__ import annotations

import base64
import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.tokens import (
    MAX_HEADER_BYTES,
    MAX_TOKEN_BYTES,
    TOKEN_TYPE,
    LocalKeySet,
    MalformedToken,
    pre_parse,
)

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]


def _segment(payload: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def _token(header: dict[str, object], payload: dict[str, object] | None = None) -> str:
    return f"{_segment(header)}.{_segment(payload or {'sub': 's'})}.c2ln"


HEADER = {"alg": "RS256", "kid": "k1", "typ": TOKEN_TYPE}


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, public


# ---------------------------------------------------------------------------
# The bound
# ---------------------------------------------------------------------------


def test_a_well_formed_header_is_accepted_and_the_payload_is_not_returned() -> None:
    """What comes out is enough to choose a key, and nothing from the payload."""
    parsed = pre_parse(_token(HEADER))
    assert parsed.algorithm == "RS256"
    assert parsed.key_id == "k1"
    assert parsed.typ == TOKEN_TYPE
    assert not hasattr(parsed, "claims")
    assert not hasattr(parsed, "payload")


def test_an_enormous_header_is_refused_here_and_accepted_by_pyjwt() -> None:
    """The measurement that makes the bound load-bearing.

    `jwt.get_unverified_header` parsed a 5.3 MB header and returned it. That is
    not a defect in PyJWT -- it bounds nothing because bounding is the caller's
    job -- but it means an unbounded caller will happily base64-decode and
    JSON-parse megabytes for every request that asks it to.
    """
    huge = _token({"alg": "RS256", "kid": "k1", "typ": TOKEN_TYPE, "pad": "A" * 4_000_000})

    assert jwt.get_unverified_header(huge)["alg"] == "RS256"

    with pytest.raises(MalformedToken, match="exceeds"):
        pre_parse(huge)


def test_a_token_over_the_byte_limit_is_refused() -> None:
    padded = _token(HEADER, {"sub": "s", "pad": "A" * MAX_TOKEN_BYTES})
    assert len(padded) > MAX_TOKEN_BYTES
    with pytest.raises(MalformedToken, match=f"exceeds {MAX_TOKEN_BYTES} bytes"):
        pre_parse(padded)


def test_the_header_bound_is_below_the_token_bound() -> None:
    """Otherwise the header check could never fire, and would be dead code."""
    assert MAX_HEADER_BYTES < MAX_TOKEN_BYTES


@pytest.mark.parametrize(
    ("token", "segments"),
    [("aaa", 1), ("aaa.bbb", 2), ("a.b.c.d", 4), ("a.b.c.d.e", 5)],
)
def test_a_token_without_three_segments_is_refused_by_count(token: str, segments: int) -> None:
    """And the message says so, which PyJWT's does not.

    Measured: a five-segment token -- the JWE shape -- fails PyJWT with
    `DecodeError: Invalid header padding`, which sends the reader to the wrong
    problem entirely.
    """
    with pytest.raises(MalformedToken, match=f"this has {segments}"):
        pre_parse(token)


def test_an_empty_segment_is_refused() -> None:
    with pytest.raises(MalformedToken, match="no empty segment"):
        pre_parse(f"{_segment(HEADER)}..c2ln")


# ---------------------------------------------------------------------------
# The header's contents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("algorithm", ["none", "HS256", "RS512", "ES256", "PS256"])
def test_an_unpermitted_algorithm_is_refused(algorithm: str) -> None:
    """Including `none`, and including algorithms that are merely not ours.

    HS256 is the one that matters: it is a *symmetric* algorithm, so a verifier
    that accepted it would verify a token signed with the public key it
    publishes.
    """
    with pytest.raises(MalformedToken, match="unpermitted algorithm"):
        pre_parse(_token({**HEADER, "alg": algorithm}))


@pytest.mark.parametrize("member", ["jku", "jwk", "x5u", "x5c", "crit", "enc", "zip"])
def test_an_unapproved_header_member_is_refused(member: str) -> None:
    """The first three are instructions to go and fetch a key."""
    with pytest.raises(MalformedToken, match="unapproved JOSE header"):
        pre_parse(_token({**HEADER, member: "anything"}))


@pytest.mark.parametrize("member", ["alg", "kid", "typ"])
def test_a_missing_required_header_member_is_refused(member: str) -> None:
    header = {key: value for key, value in HEADER.items() if key != member}
    with pytest.raises(MalformedToken, match=f"no {member!r}"):
        pre_parse(_token(header))


@pytest.mark.parametrize("typ", ["at+jwt", "jwt", "at+JWT", "application/jwt", ""])
def test_an_unpermitted_typ_is_refused(typ: str) -> None:
    """Exact, and case-sensitive. ADR 0078 chose `JWT` (D264).

    `at+jwt` is in this list rather than being the accepted value, and that is
    the correction: Run 7 wrote RFC 9068's media type here while the accepted
    ADR had already chosen `JWT`. The test moved with the constant because the
    constant was wrong, not because the test was inconvenient."""
    with pytest.raises(MalformedToken, match="unpermitted token type"):
        pre_parse(_token({**HEADER, "typ": typ}))


def test_a_non_string_header_member_is_refused() -> None:
    with pytest.raises(MalformedToken, match="is not a string"):
        pre_parse(_token({**HEADER, "kid": 1}))


def test_a_duplicate_header_member_is_refused() -> None:
    """Two `alg` values: one read by the key selector, one by a log line."""
    raw = b'{"alg": "RS256", "alg": "none", "kid": "k1", "typ": "at+jwt"}'
    segment = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(MalformedToken, match="duplicate JSON member"):
        pre_parse(f"{segment}.{_segment({'sub': 's'})}.c2ln")


def test_a_header_that_is_not_an_object_is_refused() -> None:
    segment = base64.urlsafe_b64encode(b'["RS256"]').rstrip(b"=").decode()
    with pytest.raises(MalformedToken, match="must be a JSON object"):
        pre_parse(f"{segment}.{_segment({'sub': 's'})}.c2ln")


@pytest.mark.parametrize("token", ["", "  ", "ünïcode.e30.sig"])
def test_a_token_that_is_not_ascii_or_is_empty_is_refused(token: str) -> None:
    with pytest.raises(MalformedToken):
        pre_parse(token)


def test_a_non_string_token_is_refused() -> None:
    with pytest.raises(MalformedToken, match="is text"):
        pre_parse(b"not.a.string")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------


def _jwks(*keys: dict[str, object]) -> bytes:
    return json.dumps({"keys": list(keys)}).encode()


PUBLIC_KEY = {"kty": "RSA", "kid": "k1", "alg": "RS256", "use": "sig", "n": "AQAB", "e": "AQAB"}


def test_a_public_jwks_loads_and_resolves_the_kid_a_token_names() -> None:
    keyset = LocalKeySet.load(_jwks(PUBLIC_KEY))
    resolved = keyset.resolve(pre_parse(_token(HEADER)))
    assert resolved["kid"] == "k1"


def test_a_token_naming_an_unknown_kid_is_refused_rather_than_tried_against_every_key() -> None:
    """Trying them all is how a retired key keeps verifying tokens.

    The retire step exists to close a window; a verifier that fell back to
    every key it held would keep that window open for as long as the key was
    published, which is the whole duration retirement is supposed to end.
    """
    keyset = LocalKeySet.load(_jwks(PUBLIC_KEY, {**PUBLIC_KEY, "kid": "k2"}))
    with pytest.raises(MalformedToken, match="no key with kid 'k9'"):
        keyset.resolve(pre_parse(_token({**HEADER, "kid": "k9"})))


@pytest.mark.parametrize("member", ["d", "p", "q", "dp", "dq", "qi", "oth"])
def test_a_jwks_carrying_private_material_is_refused(member: str) -> None:
    """The failure this guards against is the two halves wired the wrong way.

    The published JWKS is world-readable by design (ADR 0051) -- a 0400 file
    would imply a confidentiality the content does not have. Which means the
    consequence of a private parameter reaching it is not subtle.
    """
    with pytest.raises(MalformedToken, match="private key material"):
        LocalKeySet.load(_jwks({**PUBLIC_KEY, member: "c2VjcmV0"}))


@pytest.mark.parametrize(
    "document",
    [
        b'{"keys": []}',
        b"{}",
        b'{"keys": "not-a-list"}',
        b'{"keys": [{"kty": "RSA", "alg": "RS256"}]}',
        b'{"keys": [{"kty": "oct", "kid": "k1", "alg": "RS256"}]}',
        b'{"keys": [{"kty": "RSA", "kid": "k1", "alg": "HS256"}]}',
    ],
)
def test_an_unusable_jwks_is_refused(document: bytes) -> None:
    with pytest.raises(MalformedToken):
        LocalKeySet.load(document)


def test_two_keys_with_the_same_kid_are_refused() -> None:
    """Otherwise one silently wins and which one is an implementation detail."""
    with pytest.raises(MalformedToken, match="duplicate kid"):
        LocalKeySet.load(_jwks(PUBLIC_KEY, {**PUBLIC_KEY, "n": "different"}))


def test_a_jwks_is_read_from_a_file_and_republished_unchanged(tmp_path) -> None:
    path = tmp_path / "jwks.json"
    path.write_bytes(_jwks(PUBLIC_KEY))
    keyset = LocalKeySet.from_path(path)
    assert json.loads(keyset.as_document())["keys"] == [PUBLIC_KEY]


def test_pyjwt_would_process_a_token_this_parser_refuses(rsa_keypair) -> None:
    """The cost the bound avoids, shown rather than asserted.

    `jwt.decode` on a 5.3 MB token base64-decodes it, JSON-parses it and
    reaches signature verification before concluding it is rubbish -- 32 ms of
    work per request, measured. The pre-parser refuses it on the length of the
    string.
    """
    _, public = rsa_keypair
    huge = _token({"alg": "RS256", "kid": "k1", "typ": TOKEN_TYPE, "pad": "A" * 1_000_000})

    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(huge, public, algorithms=["RS256"], audience="a")

    with pytest.raises(MalformedToken):
        pre_parse(huge)
