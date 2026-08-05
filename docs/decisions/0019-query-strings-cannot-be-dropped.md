# 0019 — Traefik cannot drop query strings, so the path goes instead

- **Status:** Accepted
- **Date:** 2026-08-05
- **Session:** 2
- **Affects:** `infra/edge/traefik.yaml`, `test_query_parameters_are_dropped`, D11c, implementation plan §5

## Context

The plan's leak-surface table (§5) names `queryParameters.defaultMode: drop` as
the control that keeps a token out of the Traefik access log, and D11c flagged
that the offline lock check can only assert a semver floor:

> A digest cannot tell you what a config key does.

D11c then deferred the real proof to a `live_host` test — a request carrying a
random query-string sentinel, asserting the sentinel is absent from the log.
That test would have run in Run 8. The edge plane could not start in Run 6:

```
command traefik error: field not found, node: queryParameters
```

`accessLog.fields.queryParameters` does not exist in Traefik v3.5. Probed
directly against the locked digest, `accessLog.fields` accepts exactly
`defaultMode`, `headers` and `names`. Traefik has no query-parameter redaction
at all — the setting was invented, and it was invented in a threat-model table
where it read as a control that existed.

The deferral is the lesson. A configuration key that decides whether secrets
reach a log was going to be proved four runs after it was written, and what the
proof would have found is that the feature was never there. The floor-check D11c
settled for could not have caught this, and neither could any offline test that
reads the template rather than running the binary.

## Decision

Drop `RequestPath` instead.

`RequestPath` carries the query string, so removing the field is the only way to
keep query strings out of the access log. Verified against the locked digest: a
request to `/some/path?apg_sentinel=<random>` produces a log line with no
`RequestPath` and no occurrence of the sentinel anywhere.

## Consequences

**The path is gone from access logs.** That is a real operational loss and is
not being minimised. `RouterName` and `ServiceName` remain, so which route
matched is still answerable; which URL within that route is not.

The trade is accepted because the strongest inherited invariant of this project
is that no secret value reaches a log, and because the alternative is not "keep
the path and drop the query" — that option does not exist. The choice is between
logging query strings and logging neither.

**The sentinel test changes meaning and gets stronger.** It was going to assert
that a setting worked. It now asserts that a request carrying a secret-shaped
query string leaves no trace of it in the access log — which is a measurement of
the outcome rather than of the mechanism, and would have failed loudly against
the original configuration instead of never running.

**`test_query_parameters_are_dropped` asserted a key that cannot exist.** It
passed because it read the template. Rewritten to assert the field that does the
work, and renamed for what it now checks.

**Offline tests cannot validate Traefik configuration.** The only thing that
knows the schema is the binary. A CI job that starts the locked image against
the rendered configuration and asserts it does not exit would have caught this
in Run 2; it belongs in the Session 2 CI job and is recorded here as follow-up
work rather than done in the middle of a live run.
