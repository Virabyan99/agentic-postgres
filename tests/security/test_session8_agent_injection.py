"""An injection payload stays data (SEC-INJ-001, Session 8 Run 6).

`AGT-SQL-001` says no tool input accepts SQL, a fragment or a raw query string.
This module asserts the property from the attacker's side instead: given full
control of every tool input, **the structure of the upstream request does not
move**. The two are different questions and this repository has been caught by
the difference before — an allowlist can be correct and still be bypassed by a
value that changes what the allowlist's output *means*.

The payloads and the escape rule both come from measurement against the locked
PostgREST, with two owners so that an empty result could never be mistaken for a
working defence:

    title=neq.<value>, value = `zzz&limit=1`
      percent-encoded  -> 3 rows   one literal
      unencoded        -> 1 row    a filter AND a limit

That control is what makes the encoded arm mean something: without it, both
arms returned zero rows for different reasons and the first version of the
measurement proved nothing.
"""

from __future__ import annotations

import urllib.parse

import pytest

from app.mcp_lock import Operation, Resource
from app.mcp_query import Filter, QueryRefusal, build_request

pytestmark = [pytest.mark.security, pytest.mark.p0]

NOTES = Resource(
    name="notes",
    capability="query_notes",
    columns=("id", "owner_id", "title", "content"),
    filters={"title": ("eq", "neq", "in"), "id": ("eq", "in")},
    order_by=(("title", "asc"),),
    max_rows=200,
    required_scopes=("notes:read",),
    operation=Operation(method="get", path="/notes", operation_id="notes.get"),
)

#: Every payload a caller would actually try, in the position a caller controls.
PAYLOADS = [
    "zzz&limit=1",
    "x&owner_id=eq.00000000-0000-4000-8000-000000000000",
    "x&select=*",
    "x#fragment",
    "'; DROP TABLE app.notes; --",
    "' OR '1'='1",
    "1); SELECT pg_sleep(10); --",
    "*",
    "owner_id",
    "eq.anything",
    "(select 1)",
    "a,b",
    'q"uote',
    "back\\slash",
    "%26limit%3D1",
    "\n&limit=1",
]

#: The parameters this adapter emits, in order. Nothing a caller sends may add
#: to this list, remove from it, or reorder it.
EXPECTED_PARAMETERS = ["select", "title", "order", "limit"]


def _parameters(target: str) -> list[str]:
    query = target.split("?", 1)[1]
    return [pair.split("=", 1)[0] for pair in query.split("&")]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_a_payload_in_a_filter_value_does_not_change_the_request_structure(
    payload: str,
) -> None:
    """SEC-INJ-001, for a scalar operand."""
    target = build_request(
        NOTES, timeout_ms=5000, columns=["title"], filters=[Filter("title", "eq", payload)]
    ).target

    assert target.count("?") == 1, f"{payload!r} introduced a second query string"
    assert _parameters(target) == EXPECTED_PARAMETERS, f"{payload!r} changed the parameters"
    assert "#" not in target, f"{payload!r} introduced a fragment"
    # The payload survives as ONE encoded value, and decoding recovers it
    # exactly -- so it reached the database as data and as nothing else.
    filter_value = dict(urllib.parse.parse_qsl(target.split("?", 1)[1], keep_blank_values=True))
    assert filter_value["title"] == f"eq.{payload}"


@pytest.mark.parametrize("payload", PAYLOADS)
def test_a_payload_in_an_in_list_member_does_not_escape_the_list(payload: str) -> None:
    """SEC-INJ-001, for the list position -- the one with its own syntax.

    A comma here would split the member, and percent-encoding does not remove it
    (measured). The member is quoted and backslash-escaped, so the list has
    exactly as many members as the caller supplied.
    """
    target = build_request(
        NOTES,
        timeout_ms=5000,
        columns=["title"],
        filters=[Filter("title", "in", [payload, "sentinel"])],
    ).target

    assert _parameters(target) == EXPECTED_PARAMETERS
    decoded = dict(urllib.parse.parse_qsl(target.split("?", 1)[1], keep_blank_values=True))
    value = decoded["title"]
    assert value.startswith("in.(") and value.endswith(")")
    assert value.count('"') >= 4, "both members must be quoted"
    # The sentinel is still its own member, so the payload did not consume it.
    assert value.endswith(',"sentinel")')


def test_a_payload_in_a_COLUMN_position_is_refused_rather_than_escaped() -> None:
    """The other position a caller controls, and it is not escapable.

    A column name is an identifier, not a value: there is no encoding that makes
    an arbitrary one safe, so the only correct answer is the lock's allowlist.
    """
    # Not in the lock at all, in either position.
    for payload in ("owner_id; DROP TABLE app.notes", "*", "title,content", "notes.title"):
        with pytest.raises(QueryRefusal):
            build_request(NOTES, timeout_ms=5000, filters=[Filter(payload, "eq", "x")])
        with pytest.raises(QueryRefusal):
            build_request(NOTES, timeout_ms=5000, columns=[payload])

    # `content` is a real COLUMN and not a filterable one, so the two positions
    # answer differently -- which is the point of checking each against its own
    # list rather than against one set of names.
    assert "select=content" in build_request(NOTES, timeout_ms=5000, columns=["content"]).target
    with pytest.raises(QueryRefusal):
        build_request(NOTES, timeout_ms=5000, filters=[Filter("content", "eq", "x")])


def test_the_operator_position_is_a_closed_enum() -> None:
    """No operator arrives from a caller that the lock did not already permit."""
    for payload in ("like", "ilike", "cs", "not.eq", "eq.eq", "or"):
        with pytest.raises(QueryRefusal):
            build_request(NOTES, timeout_ms=5000, filters=[Filter("title", payload, "x")])


def test_a_benign_value_still_produces_a_working_filter() -> None:
    """**The control for every refusal above.**

    Without it, a `build_request` that refused or mangled everything would pass
    the whole module -- which is exactly how the first version of Run 6's live
    injection measurement came out green while proving nothing.
    """
    target = build_request(
        NOTES, timeout_ms=5000, columns=["title"], filters=[Filter("title", "eq", "alpha")]
    ).target

    assert "title=eq.alpha" in target
    assert _parameters(target) == EXPECTED_PARAMETERS
