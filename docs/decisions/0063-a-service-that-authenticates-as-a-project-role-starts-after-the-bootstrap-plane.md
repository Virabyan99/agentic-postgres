# 0063 — A service that authenticates as a project role starts after the bootstrap plane

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0037](0037-an-installed-launcher-resolves-a-release-and-nothing-else.md)
Affects: DEP-BOOT-001, API-SCHEMA-001, SEC-ANON-001

## Context

The first Session 5 deploy of a real project failed with PostgREST unhealthy:

```
FATAL: password authentication failed for user "apg_alpha_dev_postgrest_authenticator"
       password retrieved from file "/run/secrets/postgrest_authenticator_pgpass"
```

The secret was mounted and read; the credential was correct. The catalog said
what was actually wrong:

```
apg_alpha_dev_postgrest_authenticator|f      <- rolcanlogin
apg_alpha_dev_app_runtime|t
apg_alpha_dev_migration_user|t
```

Eleven of the thirteen roles are created `NOLOGIN` with a **null password
verifier** and stay that way until a session activates them (ADR 0046).
`postgrest_authenticator` is activated by `apply_credential` inside
`bin/postgres-bootstrap.sh --apply`, which is **step 6** of the deploy.
PostgREST is started in **step 5**, and its healthcheck is `postgrest --ready`,
which requires a working database connection.

So the deploy starts a service that authenticates as a role the next step
activates. `--wait` never returns, step 6 never runs, and the role is never
activated. The deploy cannot complete, and re-running it cannot help.

**A null verifier reports as a password failure.** PostgreSQL answers
`password authentication failed`, not "role is not permitted to log in", because
SCRAM has no verifier to check against. "Wrong password" and "role not
activated" are one symptom with two causes, and only the catalog separates them.
That is why this took a `pg_roles` query to diagnose rather than a log line.

Nothing caught it earlier because PostgREST is the first **long-running service
held to a healthcheck** that authenticates as a project role. `migration_user`
is activated by the same step and never hit this: dbmate is run on demand, after
the bootstrap, and is not waited on. `app_runtime` is used by PgBouncer, whose
healthcheck authenticates as its own admin user from its own secret, so a
client-side login failure would surface per connection rather than at start.

The ordering also cannot simply be inverted. A greenfield project has no cluster
at all, so the bootstrap plane has nothing to connect to until the data plane is
up. "Bootstrap first" and "start first" are each correct for one case.

## Decision

**The deploy starts the data plane, bootstraps, then starts the services that
depend on the bootstrap, and attaches the edge last.**

`bin/project-runtime.sh up` gains `--defer SERVICE[,SERVICE...]`. Deferred
services are excluded from the `--wait` set, and — because a project whose API
is not up must not be advertised — the edge attachment is deferred with them. A
new `resume` action brings up everything and then attaches.

`resume` deliberately does **not** re-materialize secrets. `up` writes a *new*
generation on every invocation and repoints the project at it, so a second `up`
between the bootstrap and the API start would set the role's password from one
generation and mount another into the container. That is the same failure
wearing a different cause, and it is why this is a distinct action rather than a
second `up`.

The deferred set is declared once, in `runtime_override.POST_BOOTSTRAP_SERVICES`,
and derived from there by the deploy. It is a property of the **service** — "it
authenticates as a project role the bootstrap plane activates" — not of the
session, and not of a Compose profile. Deferring "the profile of the session
being deployed" was the obvious alternative and is wrong: a greenfield deploy
through session 6 would bring up session 5's PostgREST in the first phase and
deadlock exactly as before.

Systemd is unaffected. `project-runtime.sh up` with no `--defer` behaves as it
always has — materialize, start everything, attach — which is correct on a
restart, where every role is already activated.

## Consequences

- A greenfield session-5 deploy completes without an operator running the
  bootstrap by hand between two failed attempts, which is what unblocked the
  deploy this ADR came out of.
- **The edge attachment moves to the end of the deploy**, after the API plane is
  healthy. That is §4.1's "the route is added last" and it closes the gap
  recorded as D177 — not as a side effect worth ignoring, but as the second
  reason to prefer this shape over a narrower fix.
- Adding a service that authenticates as an activated role means adding it to
  `POST_BOOTSTRAP_SERVICES`. A service added without it fails the way PostgREST
  did, which is loud, immediate, and now explained by this file.
- `test_the_project_runtime_attaches_after_starting_and_detaches_before_stopping`
  is **replaced by a stricter form** under this ADR. It anchored on the literal
  `"${profiles[@]}" up` and recorded that "that string appears once, in the arm
  that starts containers"; `resume` is a second such arm, so the anchor found
  one arm's start and compared it against another arm's attach. The replacement
  reads each arm separately, which the old form could not: it now also refuses a
  `resume` that attaches before it starts, and a `resume` that materializes.
- `check_violations` in `bin/postgres-bootstrap.py` still does not inspect
  `rolcanlogin`, so `--check` reported one violation while `--apply` ran 49
  statements. That gap is real and is left for Run 10: it is a reporting
  weakness, not a correctness one, and widening it here would be a second change
  under one ADR.
