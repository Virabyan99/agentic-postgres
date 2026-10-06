"""`app.totp` against RFC 4226 and RFC 6238, offline (CTL-TOTP-001, ADR 0252).

The RFCs' own appendix vectors are the independent implementation: rig 37a
matched all sixteen before the module existed, and these are the same values
read from the same appendices. The window and the replay rule are the
product's own and are proved beside a control each.
"""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import pytest

from app import totp

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

#: RFC 4226 Appendix D: the ASCII key "12345678901234567890", counters 0-9.
RFC_KEY = b"12345678901234567890"
RFC_4226 = ("755224 287082 359152 969429 338314 254676 287922 162583 399871 520489").split()

#: RFC 6238 Appendix B, the SHA-1 column, eight digits.
RFC_6238 = {
    59: "94287082",
    1111111109: "07081804",
    1111111111: "14050471",
    1234567890: "89005924",
    2000000000: "69279037",
    20000000000: "65353130",
}

SEED = bytes(range(20))
NOW = 1_759_600_000


def test_rfc_4226_vectors() -> None:
    assert [totp.hotp(RFC_KEY, counter) for counter in range(10)] == RFC_4226


def test_rfc_6238_vectors() -> None:
    for moment, expected in RFC_6238.items():
        assert totp.totp(RFC_KEY, moment, digits=8) == expected, moment


def test_the_window_is_one_step() -> None:
    """Now and one step either side verify, each at its own step; two away do not."""
    current = totp.step_of(NOW)
    for offset in (-1, 0, 1):
        moment = NOW + offset * totp.STEP_SECONDS
        assert totp.verify(SEED, totp.totp(SEED, moment), NOW, None) == current + offset
    for offset in (-2, 2):
        moment = NOW + offset * totp.STEP_SECONDS
        assert totp.verify(SEED, totp.totp(SEED, moment), NOW, None) is None, offset


def test_a_replayed_step_is_refused() -> None:
    """A code at or below the last accepted step is refused; the next is not."""
    first = totp.verify(SEED, totp.totp(SEED, NOW), NOW, None)
    assert first == totp.step_of(NOW)
    assert totp.verify(SEED, totp.totp(SEED, NOW), NOW, first) is None
    # The previous step's code is still inside the window, and still refused.
    assert totp.verify(SEED, totp.totp(SEED, NOW - 30), NOW, first) is None
    # Control: the next step's code is accepted after the first.
    later = NOW + totp.STEP_SECONDS
    assert totp.verify(SEED, totp.totp(SEED, later), later, first) == first + 1


def test_a_wrong_or_malformed_code_is_refused() -> None:
    right = totp.totp(SEED, NOW)
    wrong = "000000" if right != "000000" else "111111"
    assert totp.verify(SEED, wrong, NOW, None) is None
    for malformed in ("", "12345", "1234567", "12345a", " " + right[1:]):
        assert totp.verify(SEED, malformed, NOW, None) is None, malformed


def test_a_seed_is_twenty_random_bytes() -> None:
    seeds = {totp.new_seed() for _ in range(8)}
    assert len(seeds) == 8
    assert {len(seed) for seed in seeds} == {totp.SEED_BYTES} == {20}


def test_the_enrolment_uri_carries_the_seed_and_the_fixed_parameters() -> None:
    uri = totp.provisioning_uri("ada lovelace", SEED)
    parsed = urlparse(uri)
    assert (parsed.scheme, parsed.netloc) == ("otpauth", "totp")
    assert parsed.path == "/agentic-postgres:ada%20lovelace"
    query = {name: values[0] for name, values in parse_qs(parsed.query).items()}
    secret = query.pop("secret")
    assert base64.b32decode(secret + "=" * (-len(secret) % 8)) == SEED
    assert query == {
        "issuer": "agentic-postgres",
        "period": "30",
        "digits": "6",
        "algorithm": "SHA1",
    }
