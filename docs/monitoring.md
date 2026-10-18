# Monitoring

Two audiences, two places, and no number in both (ADR 0277, ADR 0278, ADR 0279).

- **A customer** reads their project's signals and statements through `/api/v1`:
  `apg monitoring show` and `apg insights show`. Every value comes from a sample
  the server already records in the control database, and names where it comes
  from.
- **The operator** reads the services' request lines in HyperDX, on the host's
  telemetry plane, behind an SSH forward and HyperDX's own login.

## The signals a customer reads

```
bin/monitoring.sh show [--project-key KEY] [--json]
```

`GET /v1/projects/{key}/monitoring` (viewer and above, or a key holding
`projects:read`). Each signal is a reading with the moment it was read and the
table it comes from, or *not read* with the reason. There is no threshold, no
colour and no alert: the reading and its age.

| Signal | Unit | Source |
|---|---|---|
| `state` | text | the newest usage sample (`app.control_usage_samples.state`) |
| `database_bytes` | bytes | the newest sample that read it (`app.control_usage_samples.database_bytes`) |
| `repository_bytes` | bytes | the newest sample that read it (`app.control_usage_samples.repository_bytes`) |
| `customer_connections` | count | the newest sample that read it (`app.control_usage_samples.customer_connections`) |
| `requests_last_hour` | count | the last hour's usage, counted across resets (`app.control_usage_samples.requests_counter`) |
| `db_time_last_hour` | milliseconds | the last hour's usage, counted across resets (`app.control_usage_samples.db_time_ms`) |
| `backup_status` | text | the last backups reading (`app.control_backup_readings.repository_status`) |
| `latest_recoverable_time` | instant | the last backups reading (`app.control_backup_readings.latest`) |
| `last_full_backup_at` | instant | the last backups reading (`app.control_backup_readings.last_full_at`) |
| `insights_sampled_at` | instant | the newest insight sample (`app.control_insight_samples.observed_at`) |

`services/auth-api/app/signals.py` is the list; a test holds every source to a
column that exists, and the reading function to these tables only.

## Query Insights

```
bin/insights.sh show [--project-key KEY] [--hours N] [--limit M] [--json]
```

`GET /v1/projects/{key}/insights?hours=N&limit=M` (1 to 168 hours, default 24;
1 to 50 statements, default 20). Every five minutes the server samples the
statements your database roles (`customer_app`, `customer_admin`) and the API's
request roles (`anon`, `authenticated`, `agent_reader`, `agent_writer`) ran, from
PostgreSQL's `pg_stat_statements`. The text is the one PostgreSQL normalised: a
literal is a `$1`, never your value. For each statement over the window: calls,
total and mean time, rows, rows per call, shared blocks read per call and the
cache hit ratio, counted across resets, the most time first.

- **Numbers only.** Nothing here tells you what to change: there is no finding,
  no recommendation and no confidence. To change a query plan, write a
  migration in your project's set and run `apg migrate propose`
  ([change governance](change-governance.md), *Proposing*).
- **Fewer than two samples** in the window could not be determined: the reason
  is printed and the command exits `6`. A statement's first sample in the
  window counts nothing -- it may only just have entered the top 50.
- **What is never recorded**: statements the platform's own roles run, a
  statement inside one of your functions (only the calling statement is timed),
  and any utility statement (`ALTER ROLE`, `DO`, `CREATE ...`) -- so a password
  or a block's literal cannot reach an insight.
- Samples are kept 7 days.

**DB time** -- the time your statements spent executing -- is part of usage
(`apg usage show`, `db_time`) and of the signals (`db_time_last_hour`), read from
the same extension and counted across resets.

## The operator's telemetry plane

The plane is one compose project on the host, `apg-telemetry` (ADR 0277):
ClickHouse holds the services' request lines (`apg.http.request`,
`apg.mcp.read`, the workflow worker's) for 7 days; HyperDX is the UI over them,
with its own login; MongoDB is HyperDX's own state; the gateway is the same
OpenTelemetry collector every project runs. Each project's collector stamps
the project's key on every line from its own render, whatever the line claimed,
and sends through a bounded queue: if the plane is down, a project loses lines
after a minute and serves on.

```
sudo bin/telemetry.sh --host host.yaml up       # admission first: exit 12 if it does not fit
sudo bin/telemetry.sh --host host.yaml status   # containers, limits, HyperDX's address
sudo bin/telemetry.sh --host host.yaml down     # volumes and networks kept
```

The plane is charged by admission at its ceilings (`doctor capacity` names it on
the committed line, `apg-telemetry (platform)`). Nothing is published: open the
forward from the operator's machine to the address `status` prints, then
`http://localhost:18080` -- HyperDX's session cookie is for `localhost`, not
`127.0.0.1`.

```
ssh -L 18080:<address from status>:8080 op@<host>
```

HyperDX admits **one** account: register immediately after the plane's first
`up`. In HyperDX, the connection is `http://clickhouse:8123`, user `reader`, no
password; the log source is `otel.otel_logs` (timestamp `Timestamp`, body
`Body`, service `ServiceName`, the project in `ResourceAttributes['project']`).

## What is not collected

Only the services' request lines. Not PostgreSQL's log, not Traefik's access
log, not PostgREST's, not `docker logs`. A line is the message only -- no
traceback, no attribute -- and the lines already carry no caller value (ADR
0249). The plane's volumes are not backed up: losing them loses saved searches
and at most 7 days of lines, never a customer's data.
