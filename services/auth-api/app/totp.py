"""RFC 4226 HOTP and RFC 6238 TOTP, over the standard library (ADR 0252).

The control plane's second factor, and nothing else uses it. **No new
dependency**: `hmac`, `hashlib`, `struct` and `secrets` are the whole
implementation, and the RFCs' own appendix vectors are the independent check
(rig 37a matched all ten RFC 4226 values and all six RFC 6238 SHA-1 values;
`tests/contract/test_totp.py` holds them).

**The product's parameters are fixed**: SHA-1, a 30-second step, six digits,
and a window of one step either side. They are constants rather than settings
because an authenticator app is configured once, from the enrolment URI, and a
server that changed any of them would lock out every enrolled person.

**Nothing here logs.** A seed is a key and a code is a credential for thirty
seconds; neither reaches a log line, an exception message or a `repr`
(`test_no_seed_reaches_a_log_line` plants both and reads every record). The
seed is stored by the control project's own set, readable only through its
definer functions, and its plaintext at rest is ADR 0252's stated residual risk.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct

__all__ = [
    "DIGITS",
    "ISSUER",
    "SEED_BYTES",
    "STEP_SECONDS",
    "WINDOW",
    "hotp",
    "new_seed",
    "provisioning_uri",
    "step_of",
    "totp",
    "verify",
]

#: The step, in seconds (RFC 6238's default, and what every authenticator app
#: assumes when the URI says `period=30`).
STEP_SECONDS = 30

#: Six digits in the product. The RFC 6238 vectors are eight-digit values and
#: the tests pass `digits=8` for them; nothing in the service does.
DIGITS = 6

#: One step either side of now: a phone whose clock is up to ~30 s off still
#: logs in. Two steps would double the codes an attacker may guess per attempt
#: for no person who needs it.
WINDOW = 1

#: 160 bits, RFC 4226's recommended key length for HMAC-SHA-1, and the length
#: `app.control_totp.seed` CHECKs.
SEED_BYTES = 20

#: The issuer an authenticator app shows beside the account.
ISSUER = "agentic-postgres"


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 section 5.3: HMAC-SHA-1, dynamic truncation, modulo 10^digits."""
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 10**digits).zfill(digits)


def step_of(unix_time: int) -> int:
    """The RFC 6238 time step a moment falls in (T0 = 0)."""
    return int(unix_time) // STEP_SECONDS


def totp(key: bytes, unix_time: int, digits: int = DIGITS) -> str:
    """RFC 6238: HOTP over the time step."""
    return hotp(key, step_of(unix_time), digits)


def verify(
    seed: bytes, code: str, now: int, last_step: int | None, window: int = WINDOW
) -> int | None:
    """The step `code` is valid for, or None.

    Every candidate in `[now - window, now + window]` is compared with
    `hmac.compare_digest`, and a step **at or below `last_step`** is never a
    candidate: a code already accepted is refused however recently it was
    valid. The caller records the returned step atomically
    (`app.control_totp_accept_step`), so two presentations of one code -- at
    once or in turn -- are accepted once.
    """
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = step_of(now)
    for candidate in range(current - window, current + window + 1):
        if last_step is not None and candidate <= last_step:
            continue
        if hmac.compare_digest(hotp(seed, candidate), code):
            return candidate
    return None


def new_seed() -> bytes:
    """Twenty bytes from the operating system's CSPRNG."""
    return secrets.token_bytes(SEED_BYTES)


#: RFC 3986's unreserved characters: everything else in a label is encoded.
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _percent_encoded(text: str) -> str:
    """RFC 3986 percent-encoding of everything but the unreserved characters.

    Written out rather than `urllib.parse.quote`: this service names no module
    of `urllib` outside ADR 0124's transport allowlist
    (`test_every_transport_in_the_service_is_declared_with_a_reason`), and a
    row granting a transport to a module that makes no request would be the
    guard loosened, not widened (D2102).
    """
    return "".join(
        character
        if character in _UNRESERVED
        else "".join(f"%{byte:02X}" for byte in character.encode("utf-8"))
        for character in text
    )


def provisioning_uri(username: str, seed: bytes) -> str:
    """The `otpauth://` URI an authenticator app enrols from. **Shown once.**

    The label is `issuer:username`, the username percent-encoded; the secret
    is unpadded base32, which is what the Key Uri Format expects.
    """
    secret = base64.b32encode(seed).decode("ascii").rstrip("=")
    label = f"{ISSUER}:{_percent_encoded(username)}"
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}"
        f"&period={STEP_SECONDS}&digits={DIGITS}&algorithm=SHA1"
    )
