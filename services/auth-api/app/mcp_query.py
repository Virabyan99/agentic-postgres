"""Building one upstream request, where AGT-SQL-001 actually lives.

**No SQL, no fragment, no raw query string, no path, no runtime-selected
operation.** Stated as absences that is a list any unwritten code satisfies, so
here it is a construction rule instead: every part of the request except the
caller's *values* is read from the lock, and every value is escaped for the one
position it occupies.

The danger is specific and it is not SQL injection. PostgREST takes filters in
the query string as `column=operator.value`. If a caller's value can carry a
`&` it becomes a second parameter; if it can carry a `,` inside `in.(…)` it
becomes two values. Both are caller data crossing into the position of syntax.

**The escape rule below is measured, and the obvious answers were wrong.**
Against the locked PostgREST, with two owners so an empty result could not be
mistaken for a working filter:

    title=neq.<value>, value = `zzz&limit=1`
      percent-encoded  -> 3 rows   the whole string is one literal
      unencoded        -> 1 row    parsed as a filter AND a limit

    a member containing a comma, inside in.(…)
      in.(weird,title)      -> 0    silently split into two members
      in.(weird%2Ctitle)    -> 0    PERCENT-ENCODING DOES NOT HELP
      in.("weird,title")    -> 1    quoting does

    a quoted member containing a double quote, written here with Q for the
    quote character so this docstring can contain it at all
      Qhe said QhiQQ        -> 0    naive
      Qhe said QQhiQQQ      -> 0    the SQL convention is wrong here
      Qhe said \\QhiQ\\Q      -> 1    a BACKSLASH escape is right

PostgREST decodes the query string before it parses the list, which is why
encoding cannot remove a comma from list syntax and quoting must. Both wrong
answers fail by matching **nothing**, which reads as an empty result rather than
as an error -- the worst failure mode available here.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any

from app.mcp_lock import Resource, WriteSpec

#: How each contract operator is spelled on the wire, and how many operands it
#: takes. `is_null` is the one whose wire form is not its name.
#:
#: A table rather than a chain of `if`s, so that "which operators exist" is one
#: list a reviewer reads once -- and so an operator the lock names but this
#: runtime cannot spell is a refusal rather than a silently dropped filter.
OPERATORS: dict[str, tuple[str, str]] = {
    "eq": ("eq", "scalar"),
    "neq": ("neq", "scalar"),
    "gt": ("gt", "scalar"),
    "gte": ("gte", "scalar"),
    "lt": ("lt", "scalar"),
    "lte": ("lte", "scalar"),
    "in": ("in", "list"),
    "is_null": ("is", "none"),
}

#: What `is_null` sends. A constant because it is the one operand this module
#: emits that did not come from a caller, and it must not look like one.
IS_NULL_OPERAND = "null"

#: The header the agent plane's request id travels in (ADR 0141).
#:
#: **Measured (rig6), not assumed**: PostgREST puts inbound request headers in
#: `current_setting('request.headers')::jsonb` with lowercased keys, so
#: `x-request-id` is readable from inside a function -- present when sent and
#: absent when not, which is the pair that makes it a measurement rather than an
#: observation. Nothing in this repository reads it there yet: the audit record
#: takes the id as an argument (ADR 0141), and the header is what carries it
#: into PostgREST's own log and into reach of a later migration.
REQUEST_ID_HEADER = "X-Request-Id"

#: The only headers the adapter sends upstream (ADR 0125, ADR 0127, ADR 0141).
#:
#: An allowlist rather than a copy of the caller's headers. `Prefer` alone would
#: let a caller ask for `count=exact` or `return=representation` and change the
#: response shape and cost; `Range` would move the window past the lock's
#: `max_rows`. Nothing a caller sends is forwarded, including `Accept` -- and
#: including the request id, which this process MINTS rather than accepts, so an
#: inbound header of that name is ignored and cannot make two agents' records
#: collide.
#:
#: This grew from two to three in Session 9 Run 6, and `mcp_upstream._dial`'s
#: equality guard moved in the SAME commit (D477). It stays an EQUALITY: both of
#: Session 8's allowlist failures were right to fail, and turning one into a
#: subset check is D300's shape.
FORWARDED_HEADERS = ("Authorization", "Accept", REQUEST_ID_HEADER)


class QueryRefusal(Exception):
    """The tool input is not something the lock permits.

    Names the INPUT that was rejected and never the schema: "column 'secret' is
    not queryable" is a statement about the request, where PostgREST's own
    `42703 column notes.secret does not exist` is a statement about the
    database (ADR 0097). The adapter refuses before it dials, so upstream never
    sees the value and never gets to describe it.
    """


@dataclass(frozen=True, slots=True)
class Filter:
    """One caller filter, before it is checked against the lock."""

    column: str
    operator: str
    value: Any = None


@dataclass(frozen=True, slots=True)
class UpstreamRequest:
    """A fully-built request. Every member came from the lock or was escaped.

    `body` is what the transport sends, verbatim (D477): serialized here, at
    build time, so `execute` carries no opinion about content -- until Session
    9 it hardcoded ``b"{}"``, which was enough for the argument-free
    `run_report` and for nothing else. `None` means "no body", which is every
    GET.
    """

    method: str
    path: str
    query: str
    timeout_ms: int
    body: bytes | None = None

    @property
    def target(self) -> str:
        return f"{self.path}?{self.query}" if self.query else self.path


def quote_list_member(value: str) -> str:
    """One member of an `in.(…)` list, escaped and quoted.

    Escape order matters and is the usual one: backslashes first, then quotes,
    or the escape character introduced by the second pass would be escaped by
    the first. Measured against eight awkward values -- comma, quote, backslash,
    trailing backslash, both, close-paren, dot and a plain string -- each
    compared against the same row fetched by `eq.`, which needs no list syntax
    and is therefore the answer this form has to reproduce. Eight of eight
    agreed, and a value that is absent returns nothing.

    **Not the SQL convention.** Doubling the quote was measured and matches
    zero rows.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _scalar(value: Any) -> str:
    """A caller value as a PostgREST operand.

    `bool` before `int`, because `True` would otherwise render as `1` and a
    caller asking for `status=eq.true` would be filtering on a different value
    than the one it named.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    raise QueryRefusal(
        f"a filter value must be a string, a number or a boolean, not {type(value).__name__}"
    )


def build_filter(resource: Resource, entry: Filter) -> tuple[str, str]:
    """One `column=operator.value` pair, checked against the lock and escaped.

    The order is the decision: **check, then escape, then emit.** A column the
    lock does not permit is refused here rather than by PostgREST's 400, because
    a 400 from upstream would mean the caller's string reached the query.
    """
    permitted = resource.filters.get(entry.column)
    if permitted is None:
        raise QueryRefusal(f"{entry.column!r} is not a filterable column of {resource.name!r}")
    if entry.operator not in permitted:
        raise QueryRefusal(
            f"{entry.operator!r} is not permitted on {entry.column!r}; "
            f"this resource allows {sorted(permitted)}"
        )

    spelling = OPERATORS.get(entry.operator)
    if spelling is None:
        # The lock named an operator this runtime cannot spell. A refusal, not a
        # dropped filter: silently ignoring it would widen the result set.
        raise QueryRefusal(f"{entry.operator!r} has no wire form in this runtime")
    wire, arity = spelling

    if arity == "none":
        if entry.value is not None:
            raise QueryRefusal(f"{entry.operator!r} takes no value")
        return entry.column, f"{wire}.{IS_NULL_OPERAND}"

    if arity == "list":
        if not isinstance(entry.value, list) or not entry.value:
            raise QueryRefusal(f"{entry.operator!r} takes a non-empty array of values")
        members = ",".join(quote_list_member(_scalar(item)) for item in entry.value)
        return entry.column, f"{wire}.({members})"

    if entry.value is None:
        raise QueryRefusal(f"{entry.operator!r} takes a value")
    return entry.column, f"{wire}.{_scalar(entry.value)}"


def build_request(
    resource: Resource,
    *,
    timeout_ms: int,
    columns: list[str] | None = None,
    filters: list[Filter] | None = None,
    order_by: int | None = None,
    limit: int | None = None,
) -> UpstreamRequest:
    """The whole request, from the lock and the caller's checked inputs.

    `order_by` is an **index into the lock's frozen orderings**, not a string.
    That is the difference between restricting a feature and replacing it: a
    caller-supplied order string would need a parser nobody reviewed, and the
    lock already enumerates every ordering a human approved.

    There is no unordered path. An unordered page is a different page each time,
    and a tool that paginates over one is lying about its results.
    """
    if resource.operation.method not in ("get", "post"):
        raise QueryRefusal(f"the lock names method {resource.operation.method!r}")

    parameters: list[tuple[str, str]] = []

    chosen = tuple(columns) if columns else resource.columns
    unknown = [column for column in chosen if column not in resource.columns]
    if unknown:
        raise QueryRefusal(f"{unknown} are not columns of {resource.name!r}")
    if not chosen:
        raise QueryRefusal("a projection of no columns is not a result")
    parameters.append(("select", ",".join(chosen)))

    for entry in filters or []:
        parameters.append(build_filter(resource, entry))

    if resource.order_by:
        if order_by is None:
            order_by = 0
        if not isinstance(order_by, int) or isinstance(order_by, bool):
            raise QueryRefusal("order_by is an index into this resource's permitted orderings")
        if not 0 <= order_by < len(resource.order_by):
            raise QueryRefusal(
                f"order_by must be 0..{len(resource.order_by) - 1} for {resource.name!r}"
            )
        column, direction = resource.order_by[order_by]
        parameters.append(("order", f"{column}.{direction}"))
    elif order_by is not None:
        raise QueryRefusal(f"{resource.name!r} permits no ordering")

    # The ceiling is the lock's. A caller may ask for fewer and never for more,
    # and the clamp is `min` rather than a refusal because asking for too many
    # is a reasonable thing for a client to do and a bounded answer is the right
    # reply (ADR 0127).
    rows = resource.max_rows
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise QueryRefusal("limit is a positive integer")
        rows = min(limit, resource.max_rows)
    parameters.append(("limit", str(rows)))

    # `quote_via=quote` and `safe=""`: every reserved character in a value is
    # encoded, including `&`, `=`, `+` and `/`. The default `quote_plus` would
    # render a space as `+`, which PostgREST reads as a literal plus.
    query = urllib.parse.urlencode(parameters, quote_via=urllib.parse.quote, safe="")

    return UpstreamRequest(
        method=resource.operation.method,
        path=resource.operation.path,
        query=query,
        timeout_ms=timeout_ms,
        # A read that POSTs (an RPC) sends the empty argument document; the
        # arguments a read expresses all live in the query string.
        body=b"{}" if resource.operation.method == "post" else None,
    )


def build_write_request(
    write: WriteSpec,
    *,
    timeout_ms: int,
    arguments: dict[str, Any],
) -> UpstreamRequest:
    """The write branch of request building (D477): a body and no query.

    **No `select`, no `limit`, no filters, no ordering** -- a write is
    one-to-one with its operation and projects nothing (D470), so the query
    string is empty and everything the caller says travels as the JSON argument
    document.

    Arguments are validated **by name against the lock's declared list**, in
    both directions: an unknown name is refused because a caller supplies
    values and never names (ADR 0127), and a missing name is refused because
    PostgREST resolves a function by the names supplied -- measured (rig4): a
    missing or extra name is a `404 PGRST202`, the same status as the product's
    own "no such task", so the place to stop a bad argument list is HERE, where
    the refusal can still name the input rather than the schema.

    Values must be scalars. Measured: PostgREST coerces a JSON number where the
    function takes `text` (`7` -> `"7"`), so a number is honest input; an
    object or array in an argument position is a document where a value
    belongs, and nothing in the reviewed surface takes one.
    """
    if write.operation.method != "post":  # pragma: no cover -- load_lock refuses it first
        raise QueryRefusal(f"the lock names method {write.operation.method!r} for a write")

    declared = set(write.arguments)
    supplied = set(arguments)
    unknown = sorted(supplied - declared)
    if unknown:
        raise QueryRefusal(
            f"{unknown} are not arguments of this operation; it takes {list(write.arguments)}"
        )
    missing = sorted(declared - supplied)
    if missing:
        raise QueryRefusal(
            f"this operation requires {missing}; a caller supplies a value for every "
            "declared argument"
        )

    for name, value in arguments.items():
        if not isinstance(value, (str, int, float, bool)):
            raise QueryRefusal(
                f"argument {name!r} must be a string, a number or a boolean, "
                f"not {type(value).__name__}"
            )

    body = json.dumps(
        {name: arguments[name] for name in write.arguments}, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    return UpstreamRequest(
        method=write.operation.method,
        path=write.operation.path,
        query="",
        timeout_ms=timeout_ms,
        body=body,
    )
