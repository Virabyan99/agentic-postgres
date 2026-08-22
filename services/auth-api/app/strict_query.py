"""Query-string parsing that refuses what the default stack accepts.

`strict_json` is this module's sibling and its docstring records the same defect
for request bodies: `json.loads('{"username": "alice", "username": "root"}')`
returns `{'username': 'root'}` -- last member wins, silently, and by the time
`json.loads` returns there is nothing left to notice. `GET /admin/audit` is the
first endpoint in this service to read a QUERY string, and a query string is a
multidict, so the same question had to be asked of it rather than assumed either
way.

**Measured (rig7), on the locked Starlette 0.49.3, with a control.** The control
arm sent each key exactly once and had to read back one value per key and two
pairs; it did.

* ``QueryParams("limit=1&limit=9999")["limit"]`` is ``"9999"``. **Last value
  wins, silently** -- the body defect's shape exactly. A caller that sends a
  modest bound and an enormous one gets the enormous one, and an operator
  reading the first pair out of an access log and the service acting on the
  second are both accurate about different requests.
* **Unlike a JSON body, the duplicate SURVIVES.** ``getlist("limit")`` is
  ``["1", "9999"]`` and ``multi_items()`` has both pairs. That difference is why
  this module is eleven lines of comparison rather than a parser hook: for a
  body the duplicate had to be caught during parsing because nothing afterwards
  could see it; here it is still there to be refused.
* Keys are case-sensitive: ``"Limit=1&limit=2"`` is two distinct keys, not a
  repeat. So a rejection keyed on case-folded names would refuse a request that
  is merely odd, and an allowlist that folded case would accept ``LIMIT``.
* ``"limit="`` yields ``""`` and is PRESENT, not absent. An empty value is
  therefore a supplied value and is refused by the converters below rather than
  falling through to a default -- which is the one path by which a caller could
  make a bound disappear.

**Unknown parameters are refused**, for `models.py`'s stated reason:
``extra="forbid"`` exists because without it pydantic accepts and *discards* an
unknown member, so a client's attempt to name its own authority leaves no trace
at all. A silently ignored ``?owner_id=…`` on an endpoint that has an
``agent_id`` filter is the same failure -- the caller believes it filtered.

**Nothing here is an authentication or authorization check**, and the order the
route calls it in is what makes that true: authenticate, require the scope, then
parse. A caller that has not proved who it is cannot use these refusals to
enumerate parameter names, and the reasons are returned in full because by then
the caller is an administrator (ADR 0097's line, and `_body`'s).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = ["InvalidQuery", "as_bounded_int", "as_uuid", "parse"]


class InvalidQuery(ValueError):
    """A query string refused before any domain logic ran.

    Distinct from `strict_json.MalformedBody`, and the difference is the
    caller's status rather than the parser's. A malformed body reaches
    `/auth/login`, which has no caller identity, so its reason is withheld
    (ADR 0097). Every caller of this module has already authenticated and passed
    a scope check, so the message is returned -- as `errors.InvalidRequest`, the
    422 shape reserved for an authenticated administrator.
    """


def parse(pairs: Iterable[tuple[str, str]], allowed: Sequence[str]) -> dict[str, str]:
    """Every supplied parameter, exactly once, and every name allowed.

    Takes ``request.query_params.multi_items()`` rather than the mapping,
    because the mapping is where the duplicate has already been resolved --
    ``QueryParams.__getitem__`` returns the last value and no later check could
    find the first. This is the same reason `strict_json` takes an
    ``object_pairs_hook``, arriving one layer earlier.

    Absent parameters are absent from the result. A parameter present with an
    empty value is present with an empty value; deciding what that means belongs
    to the converter, not here.
    """
    permitted = frozenset(allowed)
    seen: dict[str, str] = {}
    for name, value in pairs:
        if name in seen:
            raise InvalidQuery(f"query parameter given more than once: {name!r}")
        if name not in permitted:
            raise InvalidQuery(
                f"unknown query parameter: {name!r} "
                f"(this endpoint takes {', '.join(sorted(permitted))})"
            )
        seen[name] = value
    return seen


def as_uuid(name: str, value: str) -> UUID:
    """A supplied value that must be a uuid.

    Only ever called for a parameter that is present, so an empty string is a
    refusal rather than a default: ``?agent_id=`` means the caller believes it
    filtered, and answering the unfiltered query would be answering a different
    question than the one asked.
    """
    try:
        return UUID(value)
    except ValueError as exc:
        raise InvalidQuery(f"{name} is not a uuid") from exc


def as_bounded_int(name: str, value: str, *, minimum: int, maximum: int) -> int:
    """A supplied value that must be an integer inside an inclusive range.

    **It refuses rather than clamping**, and that is the whole point of the
    function. A clamp answers a different question than the one asked and says
    nothing about having done so, which is how a caller comes to believe it read
    the whole record; a refusal names the bound. The bound itself lives at the
    one call site, and migration 0020's reader deliberately does not restate it
    -- two bounds over one rule drift the moment either moves (D495, D463).

    **What `int()` accepts is wider than it looks, and it was measured rather
    than assumed** (rig7): surrounding whitespace, a leading ``+``, an
    underscore separator -- ``"1_0"`` is ten -- and any Unicode decimal digit,
    so ARABIC-INDIC DIGIT FIVE (U+0665) is five. ``"5.0"``, ``"0x10"`` and
    ``""`` all raise. None of the
    accepted forms is a defect here, because every one of them produces an
    integer that the range check below then has to survive; the reason to write
    them down is that the *first* three read like a permissive parser and the
    fourth reads like a bug, and neither is true of a bound.
    """
    try:
        parsed = int(value)
    except ValueError as exc:
        raise InvalidQuery(f"{name} is not an integer") from exc
    if not minimum <= parsed <= maximum:
        raise InvalidQuery(f"{name} must be between {minimum} and {maximum}")
    return parsed
