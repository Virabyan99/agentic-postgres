"""A secret an external proof holds, which pytest never prints (D2416).

pytest prints the arguments of a failing test -- and of a failing fixture -- with
`repr`, into the terminal log and the JUnit file the evidence is read from.
Session 39's first external half printed the live slot's two customer passwords
that way, from a fixture whose value was a plain `dict[str, str]`.

A `Secret` IS the value as a `str` -- psycopg, `json`, an f-string and a header
take it unchanged -- whose `repr` names no value, so a dict, tuple or fixture
holding one prints none. What is derived from it (`+`, a slice, an f-string) is
a plain `str` again: this guards what a fixture hands a test, not every string a
proof builds. `tests/contract/test_external_helpers.py` holds every fixture under
`tests/external/` that reads a secret to returning one.
"""

from __future__ import annotations


class Secret(str):
    """A `str` whose `repr` is redacted."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Secret('<redacted>')"
