"""Strict query-string parsing, and the document that has to agree with it.

`test_auth_strict_json.py`'s sibling, in the same shape and for the same reason:
every test here carries a companion assertion about what the **default** stack
does, because a test that only showed the strict parser refusing something would
not show that anything was gained.

Measured in Session 9 Run 7 (rig7) against the locked Starlette 0.49.3, with a
control arm that sent each key exactly once and had to read back one value per
key. ADR 0143.
"""

from __future__ import annotations

import pytest
from starlette.datastructures import QueryParams

from app.strict_query import InvalidQuery, as_bounded_int, as_uuid, parse

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

ALLOWED = ("agent_id", "owner_id", "limit")


# ---------------------------------------------------------------------------
# The defect, and the guard
# ---------------------------------------------------------------------------


def test_a_repeated_parameter_is_refused_and_the_default_resolves_it_silently() -> None:
    """The measurement and the guard in one place.

    `QueryParams.__getitem__` keeps the LAST value, exactly as `json.loads` keeps
    the last member. A caller that sends a modest bound and an enormous one gets
    the enormous one, and an access log written from the first pair describes a
    request that did not run.
    """
    raw = "limit=1&limit=9999"

    # What the default does. This is the half that makes the refusal mean
    # something rather than look like fussiness.
    assert QueryParams(raw)["limit"] == "9999"

    with pytest.raises(InvalidQuery, match="more than once"):
        parse(QueryParams(raw).multi_items(), ALLOWED)


def test_the_duplicate_is_still_visible_which_is_why_this_can_be_a_comparison() -> None:
    """The one structural difference from the body case, and it is worth stating.

    For a JSON body the duplicate had to be caught by an `object_pairs_hook`
    during parsing, because `json.loads` returns a dict and by then the first
    value is gone -- there is no later check that could find it. A query string
    is a multidict all the way through, so `multi_items()` still has both pairs
    and the guard is a comparison rather than a parser hook.
    """
    items = QueryParams("limit=1&limit=9999").multi_items()
    assert items == [("limit", "1"), ("limit", "9999")]
    assert QueryParams("limit=1&limit=9999").getlist("limit") == ["1", "9999"]


def test_a_parameter_repeated_three_times_is_refused_on_the_second() -> None:
    with pytest.raises(InvalidQuery, match="more than once"):
        parse(QueryParams("limit=1&limit=2&limit=3").multi_items(), ALLOWED)


def test_an_unknown_parameter_is_refused_and_the_default_discards_it_silently() -> None:
    """`extra="forbid"`'s reasoning, over the query string.

    A framework-bound parameter that nothing declares is simply not read, so a
    caller that believes it filtered is served the unfiltered answer and nothing
    tells it otherwise. On an audit endpoint that is a reader who thinks they
    scoped a search and did not.
    """
    raw = "limit=7&cursor=x"

    # The default: `cursor` is present, readable, and would be ignored by any
    # handler that only looked up the names it knew.
    assert QueryParams(raw)["cursor"] == "x"

    with pytest.raises(InvalidQuery, match="unknown query parameter"):
        parse(QueryParams(raw).multi_items(), ALLOWED)


def test_the_refusal_names_the_parameters_the_endpoint_does_take() -> None:
    """A refusal an authenticated administrator can act on.

    This is only reachable AFTER `authenticate` and `require_scope`, which is
    what makes naming them safe -- and the route's own test asserts that
    ordering, because the sentence below is exactly what must not reach an
    anonymous prober.
    """
    with pytest.raises(InvalidQuery) as raised:
        parse(QueryParams("cursor=x").multi_items(), ALLOWED)
    message = str(raised.value)
    assert "cursor" in message
    for name in ALLOWED:
        assert name in message


def test_parameter_names_are_case_sensitive_so_the_allowlist_must_be_too() -> None:
    """Measured: `Limit` and `limit` are DISTINCT keys, not a repeat.

    Both halves matter. An allowlist that folded case would accept `LIMIT` from a
    caller and read nothing; one that did not fold would refuse `Limit` as
    unknown, which is this one. And because they are distinct keys, `Limit=1&
    limit=2` is not a duplicate and must not be reported as one -- a refusal
    naming the wrong reason sends the caller to fix the wrong thing.
    """
    assert sorted(QueryParams("Limit=1&limit=2").keys()) == ["Limit", "limit"]

    with pytest.raises(InvalidQuery, match="unknown query parameter"):
        parse(QueryParams("Limit=1").multi_items(), ALLOWED)


def test_an_absent_parameter_is_absent_and_an_empty_one_is_present() -> None:
    """Measured: `"limit="` yields `""` and is PRESENT.

    The distinction is the whole reason the converters refuse an empty string
    rather than falling through to a default. A parser that treated `?limit=` as
    absent would let a caller make a bound disappear by supplying it emptily,
    which reads like supplying it.
    """
    assert parse(QueryParams("").multi_items(), ALLOWED) == {}
    assert parse(QueryParams("limit=").multi_items(), ALLOWED) == {"limit": ""}
    assert parse(QueryParams("limit=7").multi_items(), ALLOWED) == {"limit": "7"}


def test_the_order_parameters_arrive_in_does_not_change_the_result() -> None:
    """A dict keyed by name, so two orderings are one request."""
    first = parse(QueryParams("agent_id=a&limit=7").multi_items(), ALLOWED)
    second = parse(QueryParams("limit=7&agent_id=a").multi_items(), ALLOWED)
    assert first == second == {"agent_id": "a", "limit": "7"}


# ---------------------------------------------------------------------------
# The converters
# ---------------------------------------------------------------------------


def test_a_uuid_parameter_that_is_not_a_uuid_is_refused() -> None:
    assert as_uuid("agent_id", "8c9a9e2e-0d3d-4a1e-9a1b-1f0a2b3c4d5e")
    for value in ("", "not-a-uuid", "8c9a9e2e0d3d4a1e9a1b"):
        with pytest.raises(InvalidQuery, match="is not a uuid"):
            as_uuid("agent_id", value)


def test_a_bound_refuses_rather_than_clamping() -> None:
    """The property the whole two-authorities argument rests on.

    A clamp answers a different question than the one asked and says nothing
    about having done so, which is how a caller comes to believe it read the
    whole record. Migration 0020's reader applies `p_limit` without a clamp of
    its own precisely because this refusal exists; if this ever became a clamp,
    there would be no bound anywhere that a caller could observe.
    """
    assert as_bounded_int("limit", "100", minimum=1, maximum=500) == 100
    assert as_bounded_int("limit", "1", minimum=1, maximum=500) == 1
    assert as_bounded_int("limit", "500", minimum=1, maximum=500) == 500

    for value in ("0", "501", "-1", "1000000"):
        with pytest.raises(InvalidQuery, match="must be between 1 and 500"):
            as_bounded_int("limit", value, minimum=1, maximum=500)


def test_the_bound_names_its_range_so_the_caller_can_act_on_the_refusal() -> None:
    with pytest.raises(InvalidQuery) as raised:
        as_bounded_int("limit", "501", minimum=1, maximum=500)
    assert "1" in str(raised.value)
    assert "500" in str(raised.value)


def test_what_int_accepts_is_wider_than_it_looks_and_the_range_check_still_runs() -> None:
    """Measured (rig7), and written down because three of the four surprise.

    `int()` accepts surrounding whitespace, a leading `+`, an underscore
    separator, and any Unicode decimal digit. None of them is a defect for a
    bound whose job is a range check -- each produces an integer the range check
    then has to survive -- and the reason to assert them is that the first three
    read like a permissive parser and the fourth reads like a bug, and neither
    is true.
    """
    assert as_bounded_int("limit", " 5 ", minimum=1, maximum=500) == 5
    assert as_bounded_int("limit", "+5", minimum=1, maximum=500) == 5
    assert as_bounded_int("limit", "1_0", minimum=1, maximum=500) == 10
    # Written as an escape rather than the glyph: ruff's RUF001 refuses the
    # literal as visually ambiguous, and it is right to -- a reviewer cannot see
    # from the source that this is a digit at all, which is the whole finding.
    # The glyph is written as an escape: ruff refuses the literal as
    # visually ambiguous, and it is right to -- a reviewer cannot tell from
    # the source that it is a digit at all, which is the finding.
    assert as_bounded_int("limit", "\u0665", minimum=1, maximum=500) == 5

    # And the one that matters: a wide parser is still bounded.
    with pytest.raises(InvalidQuery, match="must be between"):
        as_bounded_int("limit", "5_0_1", minimum=1, maximum=500)

    for value in ("5.0", "0x10", "", "five"):
        with pytest.raises(InvalidQuery, match="is not an integer"):
            as_bounded_int("limit", value, minimum=1, maximum=500)


# ---------------------------------------------------------------------------
# The document and the parser are one surface (D274)
# ---------------------------------------------------------------------------


def test_the_documented_query_parameters_are_the_parsed_ones() -> None:
    """The seam `openapi_docs.query_parameter` names, held by this.

    The route declares its parameters to the document and passes an allowlist to
    the parser, and nothing in the framework keeps the two in step -- that is the
    price of not letting FastAPI bind them. An endpoint whose document names a
    filter the parser rejects is D274's shape: `/docs/rest` was proved at 401 and
    200 for four runs and had never rendered, because nothing requested the
    script its own markup named.

    Read from the generated document and from `routes.py`'s constant, so a
    parameter added to one and not the other fails here.
    """
    from app import main as main_module
    from app.routes import AUDIT_QUERY_PARAMETERS

    document = main_module.create_app("auth").openapi()
    declared = {
        parameter["name"] for parameter in document["paths"]["/admin/audit"]["get"]["parameters"]
    }
    assert declared == set(AUDIT_QUERY_PARAMETERS), (
        f"the document names {sorted(declared)} and the parser accepts "
        f"{sorted(AUDIT_QUERY_PARAMETERS)}"
    )


def test_the_documented_limit_range_is_internally_coherent() -> None:
    """What this CAN distinguish, which is less than its first version claimed.

    **The first version compared two constants and the battery caught it.** It
    read `maximum` out of the generated document and compared it to
    `AUDIT_LIMIT_MAX` -- and the document's `maximum` *is* `AUDIT_LIMIT_MAX`,
    emitted from it three lines away in `routes.py`. Both sides move together, so
    a route that documented 500 and enforced a literal 100 passed. CLAUDE.md
    section 6 names that exactly: *a test comparing two constants is not testing
    the thing between them*.

    So this asserts the two things the document alone can be wrong about, and
    the ENFORCED bound is measured against a real endpoint in
    `test_auth_endpoints.py`, which sends the advertised boundary and one past
    it.

    The coherence half is not filler. A default outside the advertised range
    would be a documented request that the endpoint refuses **by default** -- a
    contradiction a caller finds by making the simplest possible request.
    """
    from app import main as main_module
    from app.routes import AUDIT_LIMIT_DEFAULT, AUDIT_LIMIT_MAX, AUDIT_LIMIT_MIN

    document = main_module.create_app("auth").openapi()
    parameters = document["paths"]["/admin/audit"]["get"]["parameters"]
    limit = next(parameter for parameter in parameters if parameter["name"] == "limit")
    schema = limit["schema"]

    # Present at all: a fragment that lost its bounds would advertise an
    # unbounded integer, which is a contract this endpoint does not honour.
    for member in ("minimum", "maximum", "default"):
        assert member in schema, f"the published limit schema has no {member}"

    assert schema["minimum"] < schema["maximum"], schema
    assert schema["minimum"] <= schema["default"] <= schema["maximum"], (
        f"the default {schema['default']} sits outside the advertised range, so the "
        "simplest possible request is one the document says is illegal"
    )
    assert (AUDIT_LIMIT_MIN, AUDIT_LIMIT_DEFAULT, AUDIT_LIMIT_MAX) == (
        schema["minimum"],
        schema["default"],
        schema["maximum"],
    ), "the fragment is no longer generated from the constants the route reads"


def test_no_query_parameter_names_a_principal_the_caller_could_become() -> None:
    """SEC-PARAM-001's neighbourhood, asserted where it could regress.

    `agent_id` and `owner_id` are FILTERS over a record the caller is already
    authorized to read in full, so they narrow a permitted read rather than
    authorize one. What must never appear here is a parameter that decides
    AUTHORITY -- a role, a scope, an owner to act as -- because that is the shape
    the agent plane's audit functions have no argument for at all (D473).
    """
    from app.routes import AUDIT_QUERY_PARAMETERS

    forbidden = {"role", "scope", "scopes", "act_as", "as_user", "as_owner", "token_use"}
    assert not forbidden & set(AUDIT_QUERY_PARAMETERS)
