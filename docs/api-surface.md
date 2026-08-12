# The API surface

What Session 5 publishes over HTTP, who may reach it, and which document is the
authority when two of them disagree.

Background: [database security](database-security.md) ·
[project isolation](project-isolation.md) ·
[ADR 0050](decisions/0050-the-published-surface-is-a-reviewed-allowlist.md).

## The four authorities, in order

OpenAPI is not one of them, and that is the point.

1. **`contracts/postgrest-api-surface.yaml`** — the reviewed intent. What this
   deployment means to publish.
2. **The PostgreSQL catalog and its ACLs** — what is actually there. A grant is
   the only thing that makes an object reachable.
3. **`contracts/postgrest-openapi.canonical.json`** — the normalized snapshot, and
   the generated client contract.
4. **The documentation page** — presentation only.

An object present in `api` and absent from (1) is a **release failure**, even
when its grants keep it out of OpenAPI, because the next grant change would
publish it.

## What is published

| Surface | Methods | Authority |
|---|---|---|
| `api.notes` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.tasks` | `GET`, `HEAD` | security-invoker view; the caller's row policy applies |
| `api.create_note(p_title, p_content)` | `POST` | `SECURITY DEFINER`, safe only because the base tables carry FORCE RLS |
| `api.update_task_status(p_task_id, p_expected_status, p_new_status)` | `POST` | ADR 0003's operation 4 |

Argument names carry the `p_` prefix the functions actually have, because
PostgREST maps JSON body keys onto parameter names.

## The document advertises three verbs it will refuse

Measured, and recorded rather than fixed (ADR 0060).

`openapi-mode = follow-privileges` publishes `DELETE`, `PATCH` and `POST` on both
views, because the documentation role holds `EXECUTE` on the write RPCs — and
**all three return 403**. No PostgREST setting filters methods by grant, so the
generated document cannot be made to agree with the surface.

The documentation page says so in its own text, above the reference. A page that
showed those verbs silently would be the first thing in this deployment to lie
about what it does.

## Authorization is PostgreSQL's, not PostgREST's

PostgREST is transport. Every read passes through a security-invoker view over a
FORCE-RLS table; every write derives ownership rather than accepting it.

The request identity is the transaction-local claim `app.user_id`
(ADR 0029) — **trusted, not authenticated**. That is exactly why
`app_private.postgrest_pre_request()` refuses to set it from anything but a
validated token, and why the hook is the only thing that sets it.

Four things the hook does, in order, and each was a defect before it was a
clause:

1. **Carries the role's `statement_timeout` into the transaction.** PostgreSQL
   processes a role's settings only at login, and PostgREST reaches its request
   role with `SET LOCAL ROLE`, which is not one — so a timeout on the role
   bounded nothing until something carried it (ADR 0068).
2. **Refuses the documentation role an identity**, and refuses a documentation
   token that carries a subject rather than ignoring it. The difference between
   "this credential cannot act" and "this credential's request was quietly
   reinterpreted" is the difference between a refusal somebody can debug and a
   permission that returns when a policy changes.
3. **Reads the validated claims once**, and fails closed if they are unreadable:
   "absent" and "malformed" look identical one line later and mean opposite
   things about who is asking.
4. **Shape-checks the subject** before the row policy's cast does, which
   otherwise returned a raw `invalid input syntax for type uuid` to the caller.

## What a stranger can reach

Measured from off-host, not inferred:

- `/api/rest` answers, and answers **401** without a token.
- `/docs/rest` answers **401 with a Basic challenge** — a refusal, not a page.
- 443 and 80 are open; 80 redirects. 5432, 6432, 3000, 3001, 8080, 8443 and the
  host-loopback range 15432–15435 are closed.

The 443 half is a **positive control**: a scan that can see nothing produces the
same output as a scan that finds nothing, and only one of those is a boundary.

## Two 404s that are not the same 404

Traefik's own 404 for an unrouted host and a routed 404 from an upstream are
**identical from outside**. Read the access log before concluding anything:
Traefik's carries no `RouterName` and a 19-byte body; a routed one carries the
router, the `ServiceURL` and the upstream's body.

Run 9 produced three 404s in a row with three different causes — a container the
edge could not see, a prefix that was never stripped, and a middleware that did
not exist.

## The snapshot, and why it is captured rather than generated

`bin/api-contract.py --update` captures from a running deployment; a human
reviews the diff; the result is committed. The deployed document records three
checksums and reports `api.status: ready` only when all three are present, which
is why a project's **first** deploy can never publish one — the snapshot is
captured *from* a deployment that does not exist yet.

Two projects share one canonical snapshot digest and must publish **different**
project digests: the reviewed surface is project-neutral, and the document each
serves carries its own host.
