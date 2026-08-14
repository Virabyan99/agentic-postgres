"""Request-body parsing that refuses what the default stack accepts.

Measured in Run 7, against the locked FastAPI 0.121.2 / Starlette 0.49.3 /
pydantic 2.13.4:

* `json.loads('{"username": "alice", "username": "root"}')` returns
  `{'username': 'root'}`. **Last member wins, silently.** Starlette's
  `Request.json` is `json.loads(await self.body())` with no hook, so the
  duplicate is resolved before pydantic is given anything to validate. A log
  line written from the first value and an authorisation taken from the second
  are then both accurate and describe different requests.
* `BaseModel` without `extra="forbid"` accepts and *discards* unknown members:
  `Loose(username="a", role="admin")` validates and the model has no `role`.
  The client's attempt to name its own role leaves no trace at all. With
  `extra="forbid"` it is refused -- measured, `extra_forbidden`.
* A non-object root parses happily into a list, a string, an int, a bool or
  None, each of which reaches a model as a validation error phrased in terms of
  fields that were never present.

None of that is a defect in any of the three libraries. It is the shape of the
default, and API-AUTH-002 says this service does not have the default.

**The bound comes first, and it comes first only among the things here.** The
size check runs before the parse, because a parser that has already allocated
the document is a parser that has already paid for it. It does **not** come
before the read: the caller does ``parse_object(await request.body())`` and
`request.body()` has already accumulated every byte the client sent.

Measured in Run 10 against the locked FastAPI and Starlette, with a control: a
108-byte body is read as 108 bytes, and an 8 MiB body is read **in full** and
then refused for exceeding 16 KiB -- a factor of 512, with nothing bounding it
above that. So the number below bounds the *parser*, and the *process* is
bounded one hop earlier by a Traefik buffering middleware carrying this same
value (`agentic_postgres/auth_limits.py`). Two enforcement points, one number,
and each exists for a different reason.
"""

from __future__ import annotations

import json
from typing import Any, Final

#: The largest request body this service will parse, in bytes. Every request
#: model here is a handful of short strings; the largest legitimate body is a
#: user creation carrying a display name, a username and a password, and 16 KiB
#: is roughly two hundred times that. It is a bound on memory, not a schema.
MAX_BODY_BYTES: Final = 16 * 1024


class MalformedBody(ValueError):
    """A body refused before any domain logic ran.

    One type for every reason, and the reasons are deliberately *not*
    distinguished in what the caller returns to a client: "too large",
    "duplicate member" and "not an object" are all the same answer over HTTP.
    The message is for the operator's log.
    """


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`object_pairs_hook`: the only place duplicates are still visible.

    By the time `json.loads` returns a dict the duplicate is gone -- there is
    no later check that could find it. Measured to fire on nested objects too,
    which matters because a nested duplicate is the one a reviewer skips.
    """
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise MalformedBody(f"duplicate JSON member: {key!r}")
        seen.add(key)
    return dict(pairs)


def parse_object(body: bytes) -> dict[str, Any]:
    """Parse a request body into a JSON object, strictly.

    Refuses, in order: an oversized body, a body that is not valid JSON, a
    document whose root is not an object, and an object containing a duplicate
    member at any depth.

    The order matters and is not alphabetical. Size is checked against the raw
    bytes because that is the only check that can be made without allocating;
    everything after it is about a document already in memory.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise MalformedBody("a request body is bytes")
    if len(body) > MAX_BODY_BYTES:
        raise MalformedBody(f"request body exceeds {MAX_BODY_BYTES} bytes")
    if not body.strip():
        raise MalformedBody("request body is empty")

    try:
        document = json.loads(body, object_pairs_hook=_reject_duplicates)
    except MalformedBody:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        # `json.JSONDecodeError` subclasses ValueError; UnicodeDecodeError does
        # not, and a body that is not UTF-8 arrives as one.
        raise MalformedBody(f"request body is not valid JSON: {exc}") from exc

    if not isinstance(document, dict):
        raise MalformedBody(f"request body must be a JSON object, not {type(document).__name__}")
    return document
