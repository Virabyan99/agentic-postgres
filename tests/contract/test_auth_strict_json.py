"""Strict request parsing: `API-AUTH-002`, the half that runs offline.

Each test here has a companion assertion about what the *default* stack does,
because a test that only showed the strict parser refusing something would not
show that anything was gained. Measured in Run 7 against the locked FastAPI
0.121.2 / Starlette 0.49.3 / pydantic 2.13.4.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.strict_json import MAX_BODY_BYTES, MalformedBody, parse_object

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]


def test_a_duplicate_member_is_refused_and_the_default_resolves_it_silently() -> None:
    """The measurement, and the guard, in one place.

    `json.loads` keeps the LAST value. So a log line written from the first and
    an authorisation taken from the second would both be accurate and would
    describe different requests -- and no later check could find the
    difference, because by then there is only one value.
    """
    body = b'{"username": "alice", "username": "root"}'

    assert json.loads(body) == {"username": "root"}

    with pytest.raises(MalformedBody, match="duplicate JSON member"):
        parse_object(body)


def test_a_nested_duplicate_is_refused_too() -> None:
    """The one a reviewer skips."""
    with pytest.raises(MalformedBody, match="duplicate JSON member"):
        parse_object(b'{"credentials": {"password": "a", "password": "b"}}')


def test_a_duplicate_inside_an_array_element_is_refused() -> None:
    with pytest.raises(MalformedBody, match="duplicate JSON member"):
        parse_object(b'{"scopes": [{"name": "a", "name": "b"}]}')


@pytest.mark.parametrize("body", [b"[]", b'"a string"', b"42", b"null", b"true"])
def test_a_non_object_root_is_refused(body: bytes) -> None:
    """Each of these parses happily by default, into something no model expects."""
    json.loads(body)  # the default: no error at all
    with pytest.raises(MalformedBody, match="must be a JSON object"):
        parse_object(body)


def test_an_oversized_body_is_refused_before_it_is_parsed() -> None:
    """The bound is on the raw bytes, which is the only check that allocates nothing."""
    body = b'{"a": "' + b"x" * MAX_BODY_BYTES + b'"}'
    with pytest.raises(MalformedBody, match="exceeds"):
        parse_object(body)


def test_a_body_at_the_limit_is_accepted() -> None:
    """The boundary is a limit, not an approximation of one."""
    filler = MAX_BODY_BYTES - len(b'{"a": ""}')
    body = b'{"a": "' + b"x" * filler + b'"}'
    assert len(body) == MAX_BODY_BYTES
    assert parse_object(body)["a"] == "x" * filler


@pytest.mark.parametrize("body", [b"", b"   ", b"{", b'{"a": }', b"\xff\xfe"])
def test_a_malformed_body_is_refused(body: bytes) -> None:
    with pytest.raises(MalformedBody):
        parse_object(body)


def test_a_valid_object_survives_intact() -> None:
    """The parser refuses; it does not transform."""
    assert parse_object(b'{"username": "alice", "scopes": ["api:read"]}') == {
        "username": "alice",
        "scopes": ["api:read"],
    }


def test_pydantic_discards_an_unknown_member_unless_it_is_told_not_to() -> None:
    """Why every request model in this service sets `extra="forbid"`.

    Without it, a client naming its own `role` gets a successful response and
    leaves no trace: the member is dropped during validation and never reaches
    a log, a model or a check.
    """

    class Loose(BaseModel):
        username: str

    class Strict(BaseModel):
        model_config = ConfigDict(extra="forbid")
        username: str

    loose = Loose(username="alice", role="project_admin")
    assert not hasattr(loose, "role")

    with pytest.raises(ValidationError) as raised:
        Strict(username="alice", role="project_admin")
    assert raised.value.errors()[0]["type"] == "extra_forbidden"
