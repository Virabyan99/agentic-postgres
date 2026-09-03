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

**Read this first. The first real rotation window, on 2026-08-13, found two
defects that no test could reach** (D252, D253, D254). **D252 is fixed** in
Session 6 Run 10 (ADR 0086); **D253 is still live and has no code fix.**

> **A rotated credential does not reach a running process on its own.**
>
> * ~~A credential **Traefik** holds needs `bin/edge.sh --host host.yaml
>   restart`.~~ **Fixed, and the step is gone.** The middleware named a
>   `usersFile` *path*, so the parsed configuration did not change and Traefik
>   never rebuilt the middleware — which is the only moment it re-reads that
>   file. The deploy reported success, the page kept working **with the old
>   password**, and the new one was refused. Since ADR 0086 the bcrypt hash is
>   written **inline** into the middleware document, so a rotation *is* a change
>   to what the file provider parses. Measured against the locked Traefik both
>   ways, with a control: rewriting a users file leaves the old password working;
>   rewriting the inline hash makes the new one live and refuses the old within
>   ten seconds. **No edge restart, so rotating one project's documentation
>   password no longer interrupts every other project's routes.**
> * A credential a **container mounts** needs
>   `bin/project-runtime.sh … down` before the deploy. `resume` runs
>   `compose up` without `--force-recreate`, so the container keeps the
>   generation it started with while the bootstrap plane moves the cluster's
>   password underneath it. Without the `down`, PostgREST crash-loops and the
>   REST route answers 502. **Still live.** It needs its own measurement of what
>   Compose does with a changed bind-mount source, and Run 10 did not make it.
>
> Neither was visible before, because every deploy until then materialized a new
> generation carrying **identical values** — a stale mount and a fresh one are
> the same thing when the bytes match. Five green host runs could not have
> caught either.

**No command in this repository sets a value at the provider** (D249).
`bootstrap-providers.sh --apply` creates secrets that are missing and leaves
existing ones alone, deliberately. Step 2 below is done by hand in Infisical.

**The shape is the same for all three**, and only the first and last steps
differ:

1. Capture the pre-rotation value to a root-only file. You cannot recover it
   afterwards, and a proof you cannot admit is a proof that skips.
2. Replace the value at the provider by hand, under the `provider_path` and
   `provider_key` `secrets.required.yaml` declares for it. **Confirm it saved**
   before going on — a rotation that did not happen produces a deploy that looks
   identical to one that did, and the proof's own control is what catches it.
3. **Stop the project** if the credential is one a container mounts:
   `sudo bin/project-runtime.sh --host host.yaml --project-key <key>
   --through-session 15 down`. Volumes are preserved.
4. Redeploy through session 5. This materializes a new generation and re-applies
   the credential: the bootstrap plane sets the role's verifier,
   `publish_docs_credential` rewrites the middleware document with the new hash
   inline, and `render-jwks.py` rewrites the JWKS.
5. Admit the proof with the matching `--rotated-*-from-file` flag.

There is no edge restart. Step 4 rewrites the document the file provider parses,
which is what makes Traefik rebuild the middleware and honour the new credential
(ADR 0086). Before that fix, step 4 rewrote a file the parsed configuration only
*named*, and the old password kept working.

Steps 3 and 4 are the same commands every time:

```bash
sudo bin/materialize-secrets.sh --project project.alpha.yaml \
  --requirements secrets.required.yaml --session 15

sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
  --capabilities capabilities.yaml --through-session 15
```

**The generation directory is derived, never typed.** It changes on every
materialization, and a hard-coded one silently names a superseded generation —
which is how thirteen secret proofs read the wrong file for three sessions
(D213). Every `sudo cat` below goes through this:

```bash
gen() {  # gen <project-key>
  sudo python3 -c "
import json, sys
from pathlib import Path
root = Path('/var/lib/agentic-postgres/secrets') / sys.argv[1]
print(root / 'generations' /
      json.loads((root / 'active-secret-generation.json').read_text())['generation_id'])
" "$1"
}
```

### The authenticator

The role PostgREST logs in as.

**Capture the password, not the file.** This consumer's copy is written in
`pgpass` format (ADR 0056), so the file holds `*:*:*:*:<password>` and the proof
compares your declaration against the *password*. Declaring the whole line would
make the false-declaration control incapable of failing — which is ADR 0075, and
is why the command below cuts the value out rather than copying the file:

```bash
sudo sh -c "cut -d: -f5- '$(gen alpha-dev)/postgrest/postgrest_authenticator_pgpass' \
  > /root/rotated-auth" && sudo chmod 0400 /root/rotated-auth
```

Then steps 2–4, and admit it:

```bash
sudo bin/session-05-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/alpha-dev/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/beta-dev/outputs.json \
  --rotated-authenticator-from-file /root/rotated-auth
```

**Stop the project before the deploy** (D253):

```bash
sudo bin/project-runtime.sh --host host.yaml --project-key alpha-dev \
  --through-session 15 down
```

Without it the deploy leaves PostgREST running on the generation it started
with, the bootstrap plane moves the cluster's password, and the service
crash-loops with `password authentication failed` while the route answers 502.
Measured: a container survived two deploys holding a generation two rotations
stale.

The split-brain to rule out is PostgreSQL holding one password while the running
service holds another: the plane keeps serving from connections opened before the
rotation and fails on the next reconnect, hours later. So both sides are asserted
in one run — the route serves, **and** the cluster refuses the old password.
**That split-brain is not hypothetical; the deploy path produces it.**

### The documentation credential

Basic Auth, in front of the page. Root plane, so it lands in `_root/`:

```bash
sudo cp "$(gen alpha-dev)/_root/docs_basic_auth_password" /root/rotated-docs
```

`publish_docs_credential` rewrites the middleware document on every deploy, with
the new bcrypt hash **inline** in it. That is the whole of it — redeploy, then
admit with `--rotated-docs-from-file /root/rotated-docs`.

**This used to need an edge restart and no longer does** (D252, ADR 0086). The
middleware named a `usersFile`, so the rewrite changed a file the parsed
configuration only pointed at; Traefik saw no change, rebuilt nothing, and a
middleware re-reads that file only when it is rebuilt. Measured on the host: the
new password was refused with 401 and **the old password still returned 200**,
with the correct hash sitting on disk the whole time. Re-measured offline
against the locked image, with a control, and the inline form takes effect on
its own within ten seconds.

The proof asserts the **new** password opens the page as well as that the old one
does not. A rotation Traefik never reloaded refuses both, which passes a test
that only checks the old one.

### The signing key

**Session 6 Run 10 built the overlap this section used to say did not exist.**
ADR 0076 recorded that `begin_rotation` and `complete_rotation` had no callers,
that `render-jwks.py` published one key, and that the deploy wrote
`retire_after: None` unconditionally — all true, and all now replaced. The path
is four phases and the operator surface is `bin/rotate-signing-key.sh`
(ADR 0088):

    prepare      put the new key at APG_AUTH_JWT_PREPARED_KEY and redeploy.
                 Both keys are published; the OLD one still signs, so no
                 outstanding token is affected.
    (recreate)   bring the project down and up. A running PostgREST never
                 re-reads its key set -- measured -- and after the key set file
                 has been REPLACED a `docker restart` leaves the container
                 unable to start at all. It must be recreated.
    acknowledge  `rotate-signing-key.sh … acknowledge` reads the key set out of
                 each verifier's running container and records its digest.
    promote      refused unless every verifier acknowledged the published set.
                 Then move the promoted key to APG_AUTH_JWT_SIGNING_KEY, clear
                 the prepared one, and redeploy.
    retire       refused before `retire_after`. Then redeploy and recreate.

`abandon` withdraws a prepared rotation that has not been promoted. After
promotion there is no way back and the recovery is to complete forward.

**The first use of this machinery is the issuer transition itself.** The
bootstrap issuer's key and the auth service's key are both published while both
are live, which fills the two-key ceiling — so a *further* rotation cannot be
prepared until the bootstrap issuer retires.

Capture the key **identifier**, not the key. `--rotated-jwt-from-file` takes the
retired key's public material as JSON and reads `kid` out of it, so the
identifier is all it needs — and the private key is 0400 root, mounted into no
service, copied nowhere. Take it from the deployed document, which publishes it:

```bash
sudo python3 -c "
import json
from pathlib import Path
d = json.loads(Path('/etc/agentic-postgres/projects/alpha-dev/outputs.json').read_text())
print(json.dumps({'kid': d['jwt']['active_kid']}))
" > /root/rotated-jwt
```

Then generate a new RSA private key, put **that** at the provider under
`/auth` → `APG_BOOTSTRAP_JWT_SIGNING_KEY`, run steps 3–4, and admit it with
`--rotated-jwt-from-file /root/rotated-jwt`.

The deployed document's `jwt.verification_kids` is the independent check: a key
still listed there is a key the plane still accepts, whatever one request proves.

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
