# API plane operations

Restarting it, rotating its credentials, and reading the connection budget.
Things you do to a running system rather than steps in a deployment.

Background: [the API surface](api-surface.md) ·
[pool operations](pool-operations.md) ·
[secret handling](secret-handling.md).

## The connection budget

Two roles draw on one `max_connections`, and they are bounded **together**
(ADR 0070). The arithmetic is done once, from one query, at bootstrap:

    available   = max_connections − superuser_reserved_connections   (queried live)
    api         = database.api_connection_budget                     (from the document)
    application = available − api − 5                                (the remainder)

The 5 is operational headroom, and it is what leaves a `psql` available when this
arithmetic is wrong.

On the example manifest — `max_connections` 50, `superuser_reserved` 3,
`api.rest.pool_size` 10 — the API gets **13** and the application gets **29**.

**The application gets the remainder rather than `database.pool_size`** because
it serves both the pooler's server-side pool *and* the direct access profile. A
ceiling of `pool_size` would refuse a developer's direct session whenever the
pooler was busy.

Read what is actually in force:

```sql
SELECT rolname, rolconnlimit FROM pg_roles
WHERE rolname LIKE 'apg\_%' AND rolconnlimit <> -1
ORDER BY rolname;
```

`-1` means unlimited. A role you expected to be bounded showing `-1` means the
bootstrap plane did not reach it — redeploy rather than `ALTER ROLE` by hand,
because the next deploy would overwrite the manual value anyway.

**A cluster too small for the sum refuses at bootstrap.** That is deliberate: a
negative limit means *unlimited* to PostgreSQL and `0` means *reject every
login*, so both are values it would accept and neither is what the arithmetic
meant.

## Statement timeouts

Per-role, declared in the manifest as `api.rest.statement_timeouts`, applied to
the roles by the bootstrap plane, and **carried into each request by the
pre-request hook** — which is the only reason they bind at all (ADR 0068).

```sql
SELECT r.rolname, s.setconfig
FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
ORDER BY r.rolname;
```

`bin/postgres-bootstrap.sh --check` compares that against the deployed document
and reports a role whose timeout is absent or stale. It goes red against any
cluster deployed before outputs v7, which is correct: the timeouts are genuinely
absent there.

## Restarting

Four restarts, each with a distinct failure mode. All four are proved by
`tests/deployment/test_session5_convergence.py`, which performs them itself.

| Restart | What it would break |
|---|---|
| `postgrest` alone | the JWKS mount, the schema cache, the role settings the hook reads |
| `docs` alone | nothing — the credential middleware is in Traefik's file provider, not on the container |
| the cluster underneath | the pool *and* the `LISTEN` on the reload channel, simultaneously |
| the project unit | the whole profile, through the installed launcher |

After any of them: both routes answer as themselves, the served document's digest
still matches the deployed document, and no public listener appeared — asserted
from output proved to contain 443.

**The reload channel is the one to watch.** A plane that reconnects its pool
without re-establishing its `LISTEN` answers every request correctly and never
notices a schema change again. The next migration surfaces it, one deploy later.

## Rotating a credential

Three credentials, one at a time, each in a maintenance window. Each rotation has
its own declaration flag, because a single flag would admit all three proofs on
the strength of whichever was actually rotated.

**Every rotation proof refuses a false declaration.** It asserts the value you
declared as "previous" is *not* the one now active, before it asserts anything is
refused. Without that, a window in which nothing was rotated passes every
refusal — the old credential is refused because it *is* the new credential.

### The authenticator

The role PostgREST logs in as. Write the pre-rotation value to a file first; you
cannot recover it afterwards.

```bash
sudo cat /var/lib/agentic-postgres/secrets/<key>/generations/<gen>/postgrest/... > /root/rotated-auth
sudo bin/materialize-secrets.sh --project <manifest> --session 5   # new generation
sudo ./deploy.sh --host host.yaml --project <manifest> --capabilities capabilities.yaml \
     --through-session 5
```

Then admit the proof:

```bash
sudo bin/session-05-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/<a>/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/<b>/outputs.json \
  --rotated-authenticator-from-file /root/rotated-auth
```

The split-brain to rule out is PostgreSQL holding one password while the running
service holds another: the plane keeps serving from connections opened before the
rotation and fails on the next reconnect, hours later. So both sides are asserted
in one run — the route serves, **and** the cluster refuses the old password.

### The documentation credential

Basic Auth, in front of the page. `publish_docs_credential` rewrites both the
htpasswd file and the middleware on every deploy, so a redeploy after a new
generation is the rotation.

The proof asserts the **new** password opens the page as well as that the old one
does not. A rotation Traefik never reloaded refuses both, which passes a test
that only checks the old one.

### The signing key

Two phases: publish the new key beside the old, then retire the old. The proof is
of the **second** phase only — the intermediate state accepts both by design, and
a check run there would pass whether or not the retirement ever happened.

`--rotated-jwt-from-file` takes the retired key's public material as JSON. The
deployed document's `jwt.verification_kids` is the independent check: a key still
listed there is a key the plane still accepts, whatever one request proves.

## Traps

**`ALTER ROLE ... SET` takes effect only at login.** `SET ROLE` and
`SET SESSION AUTHORIZATION` do not process role settings. Anything that must
reach a PostgREST request goes through the pre-request hook.

**`SECURITY DEFINER` changes `current_user`.** A definer function looking up "the
current role's setting" looks up the *owner's*, finds nothing, and reads exactly
like a function that ran and found nothing to do.

**A function with a `SET` clause is not the problem** — it was measured, and GUC
changes made inside one do survive to the rest of the transaction.

**`postgrest --ready` returns 0 while every request 404s.** It proves the pool and
the schema cache, not the request path. A pre-request hook that cannot resolve
does not stop the service starting.

**A middleware Traefik cannot resolve produces no router**, and the edge answers
its own 404 — indistinguishable from an unrouted host. A cross-provider
reference needs its `@file` suffix, and without it the page is served **without
asking for the password**.

**Router labels on a container the edge cannot see create no route.** The edge
filters on `Label(apg.traefik.scope, managed)`; a service on two networks also
needs `traefik.docker.network`.
