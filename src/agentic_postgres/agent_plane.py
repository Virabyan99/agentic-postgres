"""What a running agent plane is asked about itself, and how its answer is read.

**One probe, two readers.** The deploy publishes `mcp.tool_count` in the
deployed document and the doctor's *capability drift* check compares the lock
on disk against the one the document recorded; since D1153 both also need to
know which lock the RUNNING process loaded, and a second copy of the question
is a second thing to keep in step (D486, ADR 0002).

Why the question is worth asking at all. A deploy whose only change is the
capability lock recreates no container unless the container's mount digest
moved (ADR 0155), so the file on disk and the process serving requests are two
different facts. On 2026-09-11 they were two different answers: beta served six
tools and refused a tenant's scope for eight minutes while the deployed
document said seven, because the document read the file and spoke of the plane
(D1152). ADR 0195's class, in the field a reader is most likely to treat as a
statement about what is being served.

The module is pure: a string, a parse, and the arguments a caller hands
`docker`. It runs no subprocess, because the two callers already have their own
bounded runners with different failure conventions -- the deploy's `run` raises
nothing and prints, the doctor's returns `None` on a timeout -- and flattening
those here would lose the distinction each of them makes.

Nothing here loads the service package. `mcp_runtime` imports `fastmcp`,
`mcp.types` and the service's own modules, none of which exist on a host, so
the plane is reached through its container and never through an import (D292,
D445, ADR 0093).
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

#: The service label Compose gives the agent-plane container.
#:
#: A copy of `runtime_override.MCP_SERVICE` would be a second name for one
#: thing; the caller passes the value it already holds.
PROJECT_KEY_LABEL = "apg.project.key"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


#: What the agent plane is asked, inside its own container, to report about
#: itself. One line, importing the runtime module that container is serving
#: from, and printing a JSON array.
#:
#: `getattr` on `LOADED_LOCK` rather than an attribute access: a container
#: running a release older than D1153 has no such name, and a probe that raised
#: `AttributeError` there would report "the plane could not answer" for a plane
#: answering perfectly well about everything that existed when it was built.
#: The two trailing values arrive as `null` instead, which is the honest shape
#: -- this runtime does not say which lock it loaded (ADR 0195).
#: **D1286.** This runs in a FRESH interpreter (`docker exec … python -c`), not
#: in the process serving requests, so `m.LOADED_LOCK` -- which only
#: `create_mcp_app` assigns -- is `None` here however healthy the plane is. It
#: read exactly that global until Session 24's trip, and therefore answered
#: `null` on every host it was ever pointed at.
#:
#: The signature now comes from the record the SERVING process wrote, at a path
#: the module names. The module is asked for the path (`m.LOADED_LOCK_RECORD`)
#: rather than this string holding a second copy of it (D486); `getattr` with a
#: default so a plane from a release that predates the record answers `null`
#: and gets the third outcome, which is what it got before.
#:
#: `LOADED_LOCK` is still consulted, and only as a fallback: in a process that
#: DID build the app the global is the same object, and preferring the file
#: keeps the answer a statement about the running server rather than about
#: whoever imported the module last.
PROBE = (
    "import json, app.mcp_runtime as m\n"
    "record = {}\n"
    "path = getattr(m, 'LOADED_LOCK_RECORD', None)\n"
    "if path:\n"
    "    try:\n"
    "        with open(path, encoding='utf-8') as handle:\n"
    "            loaded = json.load(handle)\n"
    "        record = loaded if isinstance(loaded, dict) else {}\n"
    "    except (OSError, ValueError):\n"
    "        record = {}\n"
    "lock = getattr(m, 'LOADED_LOCK', None)\n"
    "digest = record.get('tools_sha256')\n"
    "count = record.get('tool_count')\n"
    "if digest is None and lock is not None:\n"
    "    digest, count = lock.tools_sha256, lock.tool_count\n"
    "print(json.dumps([m.PROTOCOL_REVISION, m.AUTHORIZATION_SPEC_CONFORMANT,\n"
    "                  m.ACCEPTED_TOKEN_USE, digest, count]))\n"
)


class Report(NamedTuple):
    """One plane's answer about itself.

    ``tools_sha256`` and ``tool_count`` are ``None`` when the process holds no
    lock, or is running a release that does not publish which one it loaded.
    Those two are the same value here and deliberately so: from outside, "this
    plane will not tell me which lock it serves" is one fact however it came
    about, and both are the third outcome rather than either of the first two.
    """

    protocol_revision: str
    authorization_spec_conformant: bool
    accepted_token_use: str
    tools_sha256: str | None
    tool_count: int | None


def container_filters(project_key: str, service: str) -> tuple[str, ...]:
    """The `docker ps` arguments that find one project's agent plane.

    Found by label rather than predicted: `naming` predicts Compose's container
    name and the model deliberately does not enforce it with `container_name:`
    (D55).
    """
    return (
        "--filter",
        f"label={PROJECT_KEY_LABEL}={project_key}",
        "--filter",
        f"label={COMPOSE_SERVICE_LABEL}={service}",
        "--format",
        "{{.Names}}",
    )


def sole_container(listing: str) -> str | None:
    """The one name in a `docker ps --format '{{.Names}}'` listing, or `None`.

    `None` for nought and for several: a project with two agent-plane
    containers is a state no caller here can reason about, and picking the
    first would answer a question nobody asked.
    """
    names = [line.strip() for line in listing.splitlines() if line.strip()]
    return names[0] if len(names) == 1 else None


def parse_report(stdout: str) -> Report | None:
    """Read `PROBE`'s output, or `None` if it is not what this expects.

    `None` rather than a partially-filled report: the caller's whole reason for
    asking is to publish something only when the plane confirmed it, and a
    report assembled from a half-readable answer is the guess this exists to
    avoid.
    """
    try:
        values = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(values, list) or len(values) != len(Report._fields):
        return None
    revision, conformant, accepted, tools_digest, tool_count = values
    try:
        return Report(
            protocol_revision=str(revision),
            authorization_spec_conformant=bool(conformant),
            accepted_token_use=str(accepted),
            tools_sha256=None if tools_digest is None else str(tools_digest),
            tool_count=None if tool_count is None else int(tool_count),
        )
    except (TypeError, ValueError):
        return None


def serves_lock(report: Report | None, digest: Any) -> bool | None:
    """Does this plane serve the lock whose signature is ``digest``?

    Three answers, and the third is the reason this is a function rather than an
    `==`: `True` it is that lock, `False` it is a different one, and **`None`
    this could not be determined** -- no report, a plane that does not say, or
    nothing to compare against. A caller that folded `None` into `False` would
    report drift on every plane too old to answer; one that folded it into
    `True` would publish a count nobody confirmed (ADR 0195).
    """
    if report is None or report.tools_sha256 is None:
        return None
    if not isinstance(digest, str) or not digest:
        return None
    return report.tools_sha256 == digest


__all__ = [
    "COMPOSE_SERVICE_LABEL",
    "PROBE",
    "PROJECT_KEY_LABEL",
    "Report",
    "container_filters",
    "parse_report",
    "serves_lock",
    "sole_container",
]
