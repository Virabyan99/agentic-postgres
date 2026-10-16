"""The container reads usage is made of, shared by `doctor usage` and the reconciler's sampler.

Moved here from `bin/doctor.py` in Session 41 (ADR 0275, D979) so the sampler
reads each figure exactly as the doctor does rather than through a copy: one
integer from the project's own cluster, `du -sk` inside its container, and one
instant query of the project's own Prometheus through the store container
(ADR 0168: the store is routed nowhere). Every read goes through
`container_exec.run` (ADR 0218) and returns `(value, reason)` -- a value, or
None with the reason it is not one (ADR 0195). Nothing here returns a zero for
a reading that did not arrive.
"""

# ruff: noqa: S608 -- every interpolated value is a derived role name or an instant
# the database printed, each checked against its pattern before it is used.

from __future__ import annotations

import json
import re
import subprocess
import urllib.parse

from agentic_postgres import container_exec, runtime_override

__all__ = [
    "INSTANT",
    "REQUESTS_BELOW_400_QUERY",
    "activity_sql",
    "cluster_fields",
    "cluster_int",
    "directory_kb",
    "durable_counts_sql",
    "store_value",
]

#: The edge's requests answered below 400, summed over the project's routers
#: (its exporter keeps the project's own, `rendering.py`'s keep-regex). A scan's
#: 404 is not a request a customer is making (Sheet E0, D2525, D2539).
REQUESTS_BELOW_400_QUERY = 'sum(traefik_service_requests_total{code=~"[123].."})'

#: What the database prints for `now()` and a timestamptz, as the sampler
#: passes one back as the next sample's `since`.
INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,6})?\+00$")


def cluster_fields(
    container: str, database: str, statement: str, *, separator: str = "|"
) -> tuple[list[str] | None, str]:
    """One `psql` round trip returning ONE row, its fields split; or why not."""
    try:
        answered = container_exec.run(
            container, "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
            "-F", separator, "-c", statement, timeout=20,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None, "the cluster could not be reached"
    if answered.returncode != 0:
        return None, "the cluster did not answer"
    rows = [line for line in answered.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        return None, "the cluster did not answer one row"
    return rows[0].split(separator), ""


def cluster_int(container: str, database: str, statement: str) -> tuple[int | None, str]:
    """One `psql` round trip returning one integer, parsed before it is used.

    Parsed into a value BEFORE any `diagnosis.*` call, never inside one: `int`
    could not leak text either way, but *no `.stdout` appears in a
    `diagnosis.*` call* is a rule a scan can check and a reader can apply
    without judgement (ADR 0159).
    """
    try:
        answered = container_exec.run(
            container, "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
            "-c", statement, timeout=20,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None, "the cluster could not be reached"
    if answered.returncode != 0:
        return None, "the cluster did not answer"
    try:
        return int(answered.stdout.strip()), ""
    except ValueError:
        return None, "the cluster's answer was not an integer"


def directory_kb(container: str, path: str) -> tuple[int | None, str]:
    """`du -sk` inside the cluster's own container."""
    try:
        answered = container_exec.run(container, "du", "-sk", path, user="postgres", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None, f"{path} could not be measured in the container"
    if answered.returncode != 0:
        return None, f"du reported no size for {path}"
    head = answered.stdout.strip().split()
    if not head:
        return None, f"du printed nothing for {path}"
    try:
        return int(head[0]), ""
    except ValueError:
        return None, f"du's first field for {path} was not an integer"


def store_value(
    project_key: str, query: str, *, empty: str = "the store holds no such series yet"
) -> tuple[int | None, str]:
    """One instant query against THIS project's store. `(value, reason)`.

    **Read through the container, because the store is routed nowhere** (ADR
    0168). It sits on `edge` only and publishes no port, so the only way in is
    its own network namespace -- which is exactly how the Session 14 proof
    already reads it, and the product's path is created from the proof's here
    rather than the other way round (D1582, D1114).

    The container name is DERIVED from the project key and the service
    constant, never assembled from a document field (ADR 0002).

    **Every series that comes back must name the project that was asked
    about.** The collector labels each one with `project` (ADR 0223), so a
    reply carrying another project's label means this reading reached the
    wrong store -- question 3 of the handoff's §7 -- and that is `unknown`
    with a reason rather than a number.
    """
    container = f"apg-{project_key}-{runtime_override.STORE_SERVICE}-1"
    url = (
        f"http://127.0.0.1:{runtime_override.STORE_PORT}/api/v1/query"
        f"?query={urllib.parse.quote(query)}"
    )
    try:
        answered = container_exec.run(
            container, "wget", "-q", "-Y", "off", "-O", "-", url, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return None, "the store could not be reached in its own container"
    if answered.returncode != 0:
        return None, "the store did not answer the query"

    try:
        payload = json.loads(answered.stdout)
    except ValueError:
        return None, "the store's answer was not JSON"
    if payload.get("status") != "success":
        return None, "the store reported the query unsuccessful"

    results = ((payload.get("data") or {}).get("result")) or []
    if not results:
        # Truthfully zero is NOT this case: a `sum()` over no series returns
        # an empty result, and so does a query for a metric that has never
        # existed. The two are indistinguishable from here, so the honest
        # answer is that nothing was measured. The sentence is the figure's
        # own (`STORE_EMPTY_REASONS`, D1712).
        return None, empty

    for series in results:
        labelled = (series.get("metric") or {}).get("project")
        if labelled is not None and labelled != project_key:
            return None, "the store answered for another project"

    try:
        return int(float(results[0]["value"][1])), ""
    except (KeyError, IndexError, TypeError, ValueError):
        return None, "the store's answer did not carry a number"


def activity_sql(roles: tuple[str, str]) -> str:
    """The customer roles' backends: how many, and the newest moment one of
    them did anything -- `now()` while one is not idle. No backend is a count
    of 0 and an empty instant: quiet, READ (D2539). The roles are derived
    names (`naming.database_roles`), checked before they are interpolated."""
    for role in roles:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
            raise ValueError(f"not a derived role name: {role!r}")
    names = ", ".join(f"'{role}'" for role in roles)
    return (
        "SELECT count(*), coalesce(max(CASE WHEN state IS DISTINCT FROM 'idle' THEN now() "
        "ELSE greatest(backend_start, state_change) END)::text, '') "
        f"FROM pg_stat_activity WHERE usename IN ({names})"
    )


def durable_counts_sql(since: str | None) -> str:
    """Agent calls and workflow runs CREATED since the previous sample, from
    their durable rows -- never the per-process `agent_tool_calls_total`, which
    a recreated `mcp` resets (D1609, D1643) -- the UTC day's agent calls for the
    limit notice, and the database's `now()`, the next sample's `since`.
    `since` is a value this database printed, checked before it is used; None
    (the first sample after a start) counts nothing for the window."""
    if since is not None and not INSTANT.match(since):
        raise ValueError(f"not an instant the database printed: {since!r}")
    window = (
        f"(SELECT count(*) FROM app_private.agent_audit WHERE started_at > '{since}' "
        "AND started_at <= now()), "
        f"(SELECT count(*) FROM app_private.workflow_run WHERE created_at > '{since}' "
        "AND created_at <= now())"
        if since is not None
        else "'', ''"
    )
    return (
        f"SELECT {window}, (SELECT count(*) FROM app_private.agent_audit "
        "WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'), "
        "now()::text"
    )
