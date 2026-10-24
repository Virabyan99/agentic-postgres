"""The container reads usage is made of, shared by `doctor usage` and the reconciler's sampler.

Moved here from `bin/doctor.py` in Session 41 (ADR 0275, D979) so the sampler
reads each figure exactly as the doctor does rather than through a copy: one
integer from the project's own cluster, `du -sk` inside its container, and one
instant query of the project's own Prometheus through the store container
(ADR 0168: the store is routed nowhere). Every read goes through
`container_exec.run` (ADR 0218) and returns `(value, reason)` -- a value, or
None with the reason it is not one (ADR 0195). Nothing here returns a zero for
a reading that did not arrive, unless the store shows the edge was read for
this project (`requests_below_400`, `requests_total`, ADR 0289).
"""

# ruff: noqa: S608 -- every interpolated value is a derived role name or an instant
# the database printed, each checked against its pattern before it is used.

from __future__ import annotations

import json
import re
import subprocess
import urllib.parse

from agentic_postgres import container_exec, naming, runtime_override

__all__ = [
    "CERTIFICATE_WITNESS_QUERY",
    "EDGE_READ_WITNESS_QUERY",
    "INSIGHT_STATEMENTS",
    "INSIGHT_TEXT",
    "INSTANT",
    "REQUESTS_BELOW_400_QUERY",
    "REQUESTS_TOTAL_QUERY",
    "REQUESTS_TOTAL_UNWITNESSED",
    "REQUESTS_UNWITNESSED",
    "activity_sql",
    "cluster_fields",
    "cluster_int",
    "cluster_json",
    "db_time_sql",
    "directory_kb",
    "durable_counts_sql",
    "insights_sql",
    "requests_below_400",
    "requests_total",
    "store_value",
]

#: The edge's requests answered below 400, summed over the project's routers
#: (its exporter keeps the project's own, `rendering.py`'s keep-regex). A scan's
#: 404 is not a request a customer is making (Sheet E0, D2525, D2539).
REQUESTS_BELOW_400_QUERY = 'sum(traefik_service_requests_total{code=~"[123].."})'

#: Every request the edge answered for the project, `doctor usage`'s figure
#: (`sum`, because each process of the edge mints its own series, D1609).
REQUESTS_TOTAL_QUERY = "sum(traefik_service_requests_total)"

#: ADR 0289's two witnesses, asked only when the request query answers NO
#: series (D2805: a recreated service has none until its next request). The
#: first says the collector's last scrape of the edge succeeded -- a stopped
#: edge reads `up` 0, not absent (D783), and `honor_labels` keeps `job="edge"`
#: (D784); the second says the store holds this project's own certificate
#: series, kept by the `cn` branch of the scrape filter whether or not anything
#: was asked (D782). Each selects the project by its label, so a series that
#: names no project or another one is not a witness (D2845, D2846).
EDGE_READ_WITNESS_QUERY = 'count by (project) (up{{job="edge",project="{key}"}} == 1)'
CERTIFICATE_WITNESS_QUERY = 'count by (project) (traefik_tls_certs_not_after{{project="{key}"}})'

#: Said when there is no request series and the store could not show it read
#: the edge for the project: the counter stays unread (ADR 0195).
REQUESTS_UNWITNESSED = (
    "the store holds no request answered below 400 and could not show the edge was read"
)

#: The same for `doctor usage`'s figure, which counts every answer (D2880).
REQUESTS_TOTAL_UNWITNESSED = (
    "the store holds no request series and could not show the edge was read"
)

#: `store_value`'s reason for an empty request answer: the one case the
#: witnesses are asked about.
_REQUESTS_EMPTY = "the store holds no request answered below 400"
_REQUESTS_TOTAL_EMPTY = "the store holds no request series"

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


def requests_below_400(project_key: str) -> tuple[int | None, str]:
    """The edge's sub-400 request counter for the idle decision (ADR 0276, 0289).

    A series is its value. **No series is 0 only with both witnesses** -- the
    store read the edge for this project and holds its certificate series --
    because an empty answer is also what a store that never reached the edge
    returns; with either witness missing, unanswered or another project's the
    counter is unread, named (ADR 0195). A request query the store did not
    answer keeps its own reason.
    """
    return _witnessed(project_key, REQUESTS_BELOW_400_QUERY, _REQUESTS_EMPTY, REQUESTS_UNWITNESSED)


def requests_total(project_key: str) -> tuple[int | None, str]:
    """`doctor usage`'s request figure, read as the idle decision reads its own
    (D2880, ADR 0289 amended): a series is its value; no series is 0 only with
    both witnesses, and unread with either missing. One reading of one series,
    in the report and the decision alike."""
    return _witnessed(
        project_key, REQUESTS_TOTAL_QUERY, _REQUESTS_TOTAL_EMPTY, REQUESTS_TOTAL_UNWITNESSED
    )


def _witnessed(
    project_key: str, query: str, empty: str, unwitnessed: str
) -> tuple[int | None, str]:
    """ADR 0289's rule for one request query: its series, or -- when it answers
    none -- 0 with both witnesses asked for THIS project, else unread."""
    if not naming.TRAEFIK_NAME_PATTERN.match(project_key):
        raise ValueError(
            f"project key {project_key!r} is not a Traefik name and may not be "
            "interpolated into the store's label matcher"
        )
    value, reason = store_value(project_key, query, empty=empty)
    if value is not None or reason != empty:
        return value, reason
    for witness in (EDGE_READ_WITNESS_QUERY, CERTIFICATE_WITNESS_QUERY):
        seen, _ = store_value(project_key, witness.format(key=project_key))
        if seen is None or seen < 1:
            return None, unwitnessed
    return 0, ""


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


def _checked_roles(roles: tuple[str, ...]) -> str:
    for role in roles:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):
            raise ValueError(f"not a derived role name: {role!r}")
    return ", ".join(f"'{role}'" for role in roles)


#: Session 42 (ADR 0278): how many statements one insight sample keeps, and
#: how much of each one's normalised text.
INSIGHT_STATEMENTS = 50
INSIGHT_TEXT = 2000


def insights_sql(roles: tuple[str, ...]) -> str:
    """One insight sample as ONE `jsonb` text (ADR 0278, D2568): the
    extension's `stats_reset` and the top 50 top-level statements by
    cumulative time of the given roles -- the project's customer-facing ones,
    derived by `naming.database_roles` -- in this database, counters AS READ,
    the normalised text cut to 2000. `jsonb_agg`, never `json_agg`: the
    latter prints a newline between elements, and the reader takes the whole
    answer as one document. Read as `postgres`, the extension's only reader."""
    names = _checked_roles(roles)
    return (
        "SELECT jsonb_build_object("
        "'stats_reset', (SELECT stats_reset FROM extensions.pg_stat_statements_info), "
        "'statements', coalesce((SELECT jsonb_agg(t ORDER BY t.total_exec_ms DESC) FROM ("
        "SELECT s.queryid, r.rolname AS role, s.calls, s.total_exec_time AS total_exec_ms, "
        "s.rows, s.shared_blks_hit, s.shared_blks_read, "
        f"left(s.query, {INSIGHT_TEXT}) AS query "
        "FROM extensions.pg_stat_statements s JOIN pg_roles r ON r.oid = s.userid "
        "WHERE s.toplevel "
        "AND s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) "
        f"AND r.rolname IN ({names}) "
        f"ORDER BY s.total_exec_time DESC LIMIT {INSIGHT_STATEMENTS}) t), '[]'::jsonb))::text"
    )


def db_time_sql(roles: tuple[str, ...]) -> str:
    """DB time as READ (ADR 0278, D2570): the given roles' summed top-level
    `total_exec_time` in this database, and the extension's `stats_reset`, so
    the document reads a reset rather than subtracting across one (D553)."""
    names = _checked_roles(roles)
    return (
        "SELECT (SELECT coalesce(sum(s.total_exec_time), 0) FROM extensions.pg_stat_statements s "
        "JOIN pg_roles r ON r.oid = s.userid WHERE s.toplevel AND s.dbid = "
        "(SELECT oid FROM pg_database WHERE datname = current_database()) "
        f"AND r.rolname IN ({names}))::text, "
        "coalesce((SELECT stats_reset FROM extensions.pg_stat_statements_info)::text, '')"
    )


def cluster_json(container: str, database: str, statement: str) -> tuple[object | None, str]:
    """One `psql` round trip whose WHOLE answer is one JSON document; or why not."""
    try:
        answered = container_exec.run(
            container, "psql", "-U", "postgres", "-d", database, "-X", "-qtA",
            "-c", statement, timeout=20,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None, "the cluster could not be reached"
    if answered.returncode != 0:
        return None, "the cluster did not answer (is pg_stat_statements loaded?)"
    try:
        return json.loads(answered.stdout), ""
    except ValueError:
        return None, "the cluster's answer was not one JSON document"


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
