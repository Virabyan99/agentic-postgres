"""An inbound connector's body, checked against its closed declaration (ADR 0237).

The declaration is the compiled connector's `body` -- `{members: {<name>:
{type, required, max_length | minimum, maximum}}}` -- read from the row by
`connector_inbound` AFTER the signature holds. It is a closed subset and not
JSON Schema (D1787): no schema library is pinned in this image, and a webhook
body that becomes a run's input needs names and bounds, not a language.

**The host has its own reader of the same subset**, `agentic_postgres.
connector_definition.check_body`, because this package may not import that
one. A proof feeds both twelve cases and asserts identical verdicts, so the
two are held together by a test and not by being the same file.

A refusal is a token and, for a DECLARED member, its name. Never a value, and
never an undeclared member's name: that is caller text, and the route puts
this word in a response.
"""

from __future__ import annotations

from typing import Any


def _bounded_string(value: Any, member: dict[str, Any]) -> str | None:
    if not isinstance(value, str):
        return "type"
    if len(value) > int(member.get("max_length", 8192)):
        return "too_long"
    return None


def _bounded_integer(value: Any, member: dict[str, Any]) -> str | None:
    # `True` is an `int` to Python and a boolean to the sender.
    if type(value) is not int:
        return "type"
    if value < int(member["minimum"]) or value > int(member["maximum"]):
        return "out_of_range"
    return None


def _boolean(value: Any, member: dict[str, Any]) -> str | None:
    return None if type(value) is bool else "type"


CHECKS = {"string": _bounded_string, "integer": _bounded_integer, "boolean": _boolean}


def check(declaration: dict[str, Any], body: Any) -> str | None:
    """`None` when the body is inside the declaration, else the first refusal.

    Declared members first, in name order, then anything undeclared -- the
    order the host's validator uses, so a body with two faults is refused for
    the same one by both.
    """
    if not isinstance(body, dict):
        return "not_an_object"
    members: dict[str, Any] = declaration.get("members") or {}
    for name in sorted(members):
        member = members[name]
        if name not in body:
            if member.get("required") is True:
                return "missing:" + name
            continue
        checker = CHECKS.get(member.get("type"))
        verdict = "type" if checker is None else checker(body[name], member)
        if verdict is not None:
            return verdict + ":" + name
    for name in body:
        if name not in members:
            return "unexpected_member"
    return None


__all__ = ["check"]
