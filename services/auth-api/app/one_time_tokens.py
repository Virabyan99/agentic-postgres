"""One implementation of "a single-use token and the digest that is stored".

Extracted in Session 15 Run 5, when the password-reset plane needed the same
primitive the session plane already had. **The alternative was a second minting
routine**, and two implementations of one value is the defect ADR 0002 exists to
prevent — the second one is always slightly weaker, and nothing compares them.

What lives here is the part that does not know what the token is FOR: its size,
its alphabet, and the digest a database stores instead of it. What a presented
token *means* is the caller's — `refresh_sessions.classify` for a session, and
`password_resets` for a reset — because those are different questions with
different outcomes.

**The digest is deterministic, and that is structural** (ADR 0171). Both callers
present the token ALONE, with no accompanying identifier, so the row has to be
found BY the stored value and a per-row salt would make that a full scan with a
KDF on every row. The token is 32 bytes from `os.urandom`, so the property a KDF
buys — making a guessable secret expensive to guess — is not one it needs.
"""

from __future__ import annotations

import hashlib
import re
import secrets

__all__ = ["TOKEN_ENTROPY_BYTES", "TOKEN_PATTERN", "hash_token", "is_wellformed", "mint"]

#: 32 bytes from the system CSPRNG, rendered by ``secrets.token_urlsafe`` as 43
#: url-safe characters.
TOKEN_ENTROPY_BYTES = 32

#: What a minted token looks like, so a value this deployment cannot have issued
#: is refused before it reaches a query. Not a security boundary — the digest
#: lookup is that — but a malformed token is a caller error, and answering it
#: without a database round trip is the honest shape.
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def is_wellformed(token: str) -> bool:
    """Whether this could be a token this deployment minted."""
    return bool(TOKEN_PATTERN.match(token))


def mint() -> tuple[str, str]:
    """A new token and the digest to store. **The token is a credential.**

    Returned rather than logged, printed or defaulted anywhere: the caller hands
    it to exactly one HTTP response and keeps the digest.
    """
    token = secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    """The value a database stores: a hex SHA-256, never the token.

    No constant-time comparison, and its absence is deliberate: every caller
    looks this up through a unique index, so nothing compares two digests in
    Python. A ``compare_digest`` call would imply a comparison that does not
    happen and suggest the timing question had been handled somewhere.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
