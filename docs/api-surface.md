# The API surface

What Session 5 publishes over HTTP, who may reach it, and which document is the
authority when two of them disagree.

Background: [database security](database-security.md) ·
[project isolation](project-isolation.md) ·
[ADR 0050](decisions/0050-a-reviewed-api-surface-is-a-generated-artifact.md) ·
[ADR 0198](decisions/0198-a-project-owns-a-migration-set-a-reviewed-surface-and-a-snapshot-beside-the-releases.md).

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

## A project's surface

ADR 0198. A project that declares a migration set of its own also owns a
reviewed surface and a snapshot, beside that set:

```
projects/<slug>/contracts/postgrest-api-surface.yaml      # api-surface schema 2
projects/<slug>/contracts/postgrest-openapi.canonical.json
```

**The release's contract does not gain the project's objects, and that is the
whole design.** Its header sentence has always said it is project-neutral
because the example domain is; a tenant's views living in the release's set had
made that false. With the two separated it is true again, and the release's
anti-vacuity guard keeps its equality against `{notes, tasks}` for every
adopter rather than being loosened to a containment check.

**Version 2 carries no `agent_rpcs`, no `agent_write_rpcs` and no
`forbidden_schemas`, and the schema refuses them.** All three describe the whole
database. `forbidden_schemas` is the one worth naming: it lists the schemas
nothing may ever publish, and a project able to write its own list could write a
shorter one — so the merged surface takes the release's, always. The agent
sections are the platform's until a session opens the plane to a tenant's
domain.

**The two are merged for every comparison, and a project may not redeclare a
name the release owns** — in any kind, not kind by kind. PostgREST serves
relations at `/{name}` and functions at `/rpc/{name}`, so those two do not
collide on the wire; but a project view called `notes` would replace the
release's on a deployed cluster while the release's reviewed contract still
described the old one. An enum is refused for a further reason: PostgreSQL puts
types and relations in one namespace, so a project enum named `notes` names a
catalog that cannot exist.

Both halves of the comparison move together:

```bash
# The release's surface against the release's snapshot. Every gate runs this.
bin/api-contract.sh --check

# The MERGED surface against the PROJECT's snapshot.
bin/api-contract.sh --check --project project.yaml

# The candidate, after the deploy that serves the set. Streams to stdout and
# writes nothing; the path it belongs at is printed on stderr.
sudo bin/api-contract.sh --update --project project.yaml \
  --project-outputs /home/op/<key>-outputs.json > candidate.json
```

Loading one half and not the other is the mistake the flag exists to prevent.
The merged surface against the *release's* snapshot reports every project object
as unpublished; the *release's* surface against the project's snapshot reports
every project object as reaching the document without a reviewed entry — the
case the contract exists for, fired at a project that did nothing wrong.

A project's first `--check --project` exits **5** and names the path, for the
same reason a project's first deploy can never publish a snapshot: the document
is captured *from* a deployment that does not exist yet. That is unsatisfiable
rather than unsatisfied, and the message says which.
