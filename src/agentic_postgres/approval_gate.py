"""Does every gated project RPC call the approval guard first? ADR 0242.

Migration 0037 creates `app.require_approval(p_tool)`, granted to nobody, and a
gated project function opts in by calling it as its FIRST statement. Nothing in
PostgreSQL makes a function call it, so this is the check that a project which
marks an RPC `requires_approval` actually wrote the line (D1868).

**The join nothing else makes.** The project lint reads SQL and never a
capability contract; the capability compiler reads a reviewed surface and never
a body. This module reads both: a compiled contract says which tools are gated
and which `/rpc/<name>` each one calls, and `sql_surface.final_function_bodies`
says what body the set leaves `api.<name>` with.

**Three callers, two answers** (D1868). `bin/mcp-contract.sh check --project`
and `propose` (Run 3) REFUSE on a finding; the render REPORTS it, one line on
stderr, and never refuses -- an upgrading project whose manifest rendered
yesterday must render today (an invalidated manifest is a MAJOR class, ADR
0162). A gated tool backed by a RELEASE function is reported `release_function`
by every caller and refused by none: a deployment's profile may add an approval
to a release tool, and the database cannot read a profile (D1869).

**A text reader, like `sql_surface`.** The first-statement test strips
comments and whitespace and compares keywords without case; the tool's string
literal is compared exactly, because the guard compares it exactly.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

#: The guard's own name, schema-qualified, as a project body must spell it.
GUARD = "app.require_approval"

#: The three ways a gated tool can fail the check.
NOT_FIRST = "not_first"
ABSENT = "absent"
RELEASE_FUNCTION = "release_function"
REASONS = (NOT_FIRST, ABSENT, RELEASE_FUNCTION)

#: Which of them a caller that refuses refuses. `release_function` is reported
#: and never refused (D1869).
REFUSED = frozenset({NOT_FIRST, ABSENT})

_RPC_PATH = re.compile(r"^/rpc/(\w+)$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_BEGIN = re.compile(r"\bbegin\b", re.IGNORECASE)
_MENTION = re.compile(r"\bapp\s*\.\s*require_approval\s*\(", re.IGNORECASE)


class Finding(NamedTuple):
    """One gated tool whose function does not call the guard first."""

    tool: str
    function: str
    reason: str


def _without_comments(body: str) -> str:
    body = _BLOCK_COMMENT.sub(" ", body)
    return "\n".join(line.split("--")[0] for line in body.splitlines())


def calls_guard_first(body: str, tool: str) -> bool:
    """True when the body's first statement after `BEGIN` is the guard for `tool`.

    `PERFORM app.require_approval('<tool>');`, keywords in any case, any
    whitespace between tokens, comments ignored. Anything before it -- an
    identity check, an assignment, a second guard for another tool -- is
    `not_first`, because the point of first is that nothing runs for an agent
    holding no approved decision (ADR 0242).
    """
    text = _without_comments(body)
    begin = _BEGIN.search(text)
    if begin is None:
        return False
    statement = re.compile(
        r"\s*(?i:perform)\s+(?i:app)\s*\.\s*(?i:require_approval)\s*\(\s*'"
        + re.escape(tool)
        + r"'\s*\)\s*;"
    )
    return statement.match(text, begin.end()) is not None


def gated_functions(contract: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """`(tool, function)` for every gated write tool backed by `/rpc/<function>`."""
    gated = []
    for tool in contract.get("tools", []):
        if not tool.get("requires_approval"):
            continue
        path = (tool.get("operation") or {}).get("path", "")
        matched = _RPC_PATH.match(path)
        if matched is not None:
            gated.append((tool["name"], matched.group(1)))
    return tuple(sorted(gated))


def unguarded(
    contract: dict[str, Any],
    bodies: dict[str, str],
    release_functions: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[Finding, ...]:
    """Every gated tool whose function does not call `app.require_approval` first.

    ``contract`` is a compiled capability contract (a project's own, a joint
    one, or one a profile narrowed); ``bodies`` maps an `api` function name to
    the final body the project set gives it (`sql_surface.final_function_bodies`);
    ``release_functions`` is `migrations.release_functions`' set.

    A function the project set defines is `not_first` when its body mentions
    the guard anywhere but first, and `absent` when it does not mention it. A
    release function is `release_function`. A function neither defines is
    `absent`: a gated tool whose body this check could not find is not a tool
    it may pass (ADR 0195).
    """
    findings = []
    for tool, function in gated_functions(contract):
        if function in bodies:
            body = bodies[function]
            if calls_guard_first(body, tool):
                continue
            reason = NOT_FIRST if _MENTION.search(_without_comments(body)) else ABSENT
        elif ("api", function) in release_functions:
            reason = RELEASE_FUNCTION
        else:
            reason = ABSENT
        findings.append(Finding(tool=tool, function=f"api.{function}", reason=reason))
    return tuple(findings)


def refused(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """The findings a refusing caller refuses on."""
    return tuple(finding for finding in findings if finding.reason in REFUSED)


def describe(finding: Finding) -> str:
    """One line, naming the tool, the function and ADR 0242."""
    if finding.reason == RELEASE_FUNCTION:
        return (
            f"approval gate: {finding.tool} is gated and backed by the release's "
            f"{finding.function}, which the database does not gate; its approval is a plane "
            "control only (ADR 0242, D1869)"
        )
    if finding.reason == NOT_FIRST:
        return (
            f"approval gate: {finding.tool} does not call {GUARD} first in {finding.function} "
            "(ADR 0242)"
        )
    return f"approval gate: {finding.tool} does not call {GUARD} in {finding.function} (ADR 0242)"


__all__ = [
    "ABSENT",
    "GUARD",
    "NOT_FIRST",
    "REASONS",
    "REFUSED",
    "RELEASE_FUNCTION",
    "Finding",
    "calls_guard_first",
    "describe",
    "gated_functions",
    "refused",
    "unguarded",
]
