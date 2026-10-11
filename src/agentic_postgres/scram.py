"""A SCRAM-SHA-256 server verifier, computed where the password is (ADR 0269).

`bin/endpoint.sh credential` generates a customer's database password on the
customer's own workstation, writes it to a 0600 file, and sends only what this
module computes from it: the verifier PostgreSQL stores in `pg_authid`
(RFC 5802, RFC 7677), `SCRAM-SHA-256$<iterations>:<salt>$<StoredKey>:<ServerKey>`.
The verifier authenticates nobody by itself -- a client must prove it knows the
password -- and a 256-bit random password behind it cannot be brute-forced,
which is why the control plane may hold it and must never hold the password.

PostgreSQL's own parameters: 4096 iterations and a 16-byte salt (its
`scram_iterations` default and `SCRAM_DEFAULT_SALT_LEN`), so the argument
schema's pattern can name the exact shape. The model rig 39c used is
`~/s39/run1/rig39/verifier.py`; `test_endpoint_cli` proves a verifier from
here admits its password on a real cluster and refuses another.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

ITERATIONS = 4096
SALT_BYTES = 16

#: The shape PostgreSQL stores and `schemas/operation-arguments.schema.json`
#: accepts: 22+2 base64 characters of salt, 43+1 of each 32-byte key.
VERIFIER = re.compile(
    r"SCRAM-SHA-256\$4096:[A-Za-z0-9+/]{22}==\$[A-Za-z0-9+/]{43}=:[A-Za-z0-9+/]{43}="
)


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def verifier(password: str, *, salt: bytes | None = None) -> str:
    """The server verifier for `password`, with a fresh random salt unless one
    is given (a proof reproduces one; nothing else should)."""
    if not password:
        raise ValueError("an empty password has no verifier")
    salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    if len(salt) != SALT_BYTES:
        raise ValueError(f"the salt must be {SALT_BYTES} bytes")
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    return f"SCRAM-SHA-256${ITERATIONS}:{_b64(salt)}${_b64(stored_key)}:{_b64(server_key)}"
