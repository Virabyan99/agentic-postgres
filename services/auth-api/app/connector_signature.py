"""One signing scheme, both directions (ADR 0237).

Headers: `X-Apg-Delivery: <uuid>`, `X-Apg-Event: <name>@<version>` (outbound
only) and `X-Apg-Signature: t=<unix seconds>,v1=<64 lowercase hex>`. The signed
bytes are `f"{t}.{delivery_id}.".encode("ascii") + body`, so the delivery id is
INSIDE the signature: a captured request replayed under a fresh id no longer
verifies, and the same id meets the receipt's primary key (THR-WEBHOOK-REPLAY).
HMAC-SHA256 under the connector's DERIVED key, compared with
`hmac.compare_digest`, inside `TIMESTAMP_TOLERANCE_SECONDS` either side.

Rig 34b measured this scheme against an independent signer from inside the
auth image: the image's Python, the workstation's Python and `openssl dgst
-sha256 -mac HMAC` agreed on the same bytes, and a one-byte change in the body
changed all three.

**No transport.** This module imports `hmac` and `hashlib` and reaches nothing;
the one outbound POST is `connector_delivery.py`'s. `derive` will be written
twice: here, and on the host for `bin/connector.py key` (Session 34 Run 7),
because a `bin/` command may not import a service module (ADR 0093) -- and a
proof will hold the two together.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

#: The derivation's label. Versioned, so a later scheme is a new label and
#: never a silent change of every key.
CONNECTOR_KEY_LABEL = b"apg-connector-key-v1\x00"

#: A signed request older or newer than this is refused whatever its signature.
TIMESTAMP_TOLERANCE_SECONDS = 300

NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
MASTER = re.compile(r"^[0-9a-f]{64,}$")
_HEADER = re.compile(r"^t=([0-9]{1,12}),v1=([0-9a-f]{64})$")


def derive(master_hex: str, name: str) -> str:
    """The connector's key as 64 lowercase hex characters (ADR 0237).

    Raises `ValueError` with a message that carries no value.
    """
    if not NAME.match(name):
        raise ValueError("a connector name is lowercase letters, digits and hyphens")
    master = master_hex.strip()
    if not MASTER.match(master):
        raise ValueError("the connector master is not 64 or more lowercase hex characters")
    return hmac.new(
        bytes.fromhex(master), CONNECTOR_KEY_LABEL + name.encode("ascii"), hashlib.sha256
    ).hexdigest()


def read_master(path: Path | None) -> str | None:
    """The project's `connector_signing_key`, read ONCE at start, or `None`.

    `None` when there is no file at the path (D1827: the path is always set and
    the file exists only when the project has the connectors facility), which
    turns the inbound route and the delivery pass off. A file that exists and
    is not 64+ lowercase hex raises `ValueError` naming no value: a present,
    malformed secret is a deployment defect, and the start fails on it as it
    fails on a malformed signing key.
    """
    if path is None or not path.is_file():
        return None
    master = path.read_text(encoding="ascii").strip()
    if not MASTER.match(master):
        raise ValueError("the connector key file is not 64 or more lowercase hex characters")
    return master


def signed_bytes(t: int, delivery_id: str, body: bytes) -> bytes:
    """What the signature covers: the time, the delivery id, then the raw body."""
    return f"{t}.{delivery_id}.".encode("ascii") + body


def sign(key_hex: str, t: int, delivery_id: str, body: bytes) -> str:
    """The 64-hex HMAC of one delivery under one connector's key."""
    return hmac.new(
        bytes.fromhex(key_hex), signed_bytes(t, delivery_id, body), hashlib.sha256
    ).hexdigest()


def header(t: int, digest: str) -> str:
    """`X-Apg-Signature`'s value."""
    return f"t={t},v1={digest}"


def parse(value: str | None) -> tuple[int, str] | None:
    """`(t, digest)` from a header value, or `None` for anything malformed."""
    if value is None:
        return None
    matched = _HEADER.match(value.strip())
    if matched is None:
        return None
    return int(matched.group(1)), matched.group(2)


def verify(
    key_hex: str, header_value: str | None, delivery_id: str, body: bytes, *, now: int
) -> bool:
    """Whether one request is signed by this key, now. One answer for every failure.

    A missing or malformed header, a timestamp outside the window and a wrong
    digest are all `False`: the route turns every one of them into the same 401,
    so a prober learns nothing about which it got wrong.
    """
    parsed = parse(header_value)
    if parsed is None:
        return False
    t, digest = parsed
    if abs(now - t) > TIMESTAMP_TOLERANCE_SECONDS:
        return False
    expected = sign(key_hex, t, delivery_id, body)
    return hmac.compare_digest(expected, digest)
