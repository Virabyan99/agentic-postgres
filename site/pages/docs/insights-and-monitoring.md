---
title: Query Insights and monitoring
description: Your statements' numbers, and readings that each name their source.
ledger: [query_insights, monitoring, usage]
---
# Query Insights and monitoring

## Monitoring

A short list of readings about a project, each with the moment it was read and where it comes from -- or *not read*, with the reason. There is no threshold, no colour and no alert: the reading and its age.

```
apg monitoring show --project-key KEY
```

| Reading | Unit | Comes from |
|---|---|---|
| state | text | the newest usage sample |
| database size | bytes | the newest usage sample that read it |
| backup repository size | bytes | the newest usage sample that read it |
| your connections | count | the newest usage sample that read it |
| requests in the last hour | count | the last hour's usage, counted across restarts |
| database time in the last hour | milliseconds | the last hour's usage, counted across restarts |
| backup status | text | the last backups reading |
| latest restore point | instant | the last backups reading |
| last full backup | instant | the last backups reading |
| insights sampled at | instant | the newest Query Insights sample |

The console's *Monitoring* view shows the same list.

## Query Insights

Every five minutes the server samples the statements your database roles (`customer_app`, `customer_admin`) and your API's roles ran, from PostgreSQL's `pg_stat_statements`. The text is the one PostgreSQL normalised: a literal is a placeholder such as `$1`, never your value. For each statement over the window: calls, total and mean time, rows, rows per call, blocks read per call and the cache hit ratio, counted across restarts, the most time first.

```
apg insights show --project-key KEY --hours 24 --limit 20
```

- **Numbers only.** Nothing here tells you what to change: there is no finding, no recommendation and no confidence.
- **Fewer than two samples** in the window could not be determined: the reason is shown, and the command exits 6.
- **What is never recorded**: statements the platform's own roles run, a statement inside one of your functions (only the calling statement is timed), and any utility statement such as `ALTER ROLE` or `DO` -- so a password or a block's literal cannot reach an insight.
- Samples are kept 7 days.

**Database time** -- the time your statements spent executing -- is part of usage (`apg usage show`) and of the readings above.

Something here wrong or missing? Write to [invite@agenticpostgresql.com](mailto:invite@agenticpostgresql.com).
