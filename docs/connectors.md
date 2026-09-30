# Connectors

A **connector** is how an event leaves a deployment, how a signed request from
outside starts a run, and how a run starts on a clock (ADR 0236). Every one is
a reviewed file in your project's set, installed **disabled** by the deploy,
and enabled by an administrator -- and none holds more than the agent identity
it acts for.

| Kind | What starts it | What it does |
|---|---|---|
| `outbound` | an event your own SQL emits | POSTs it, signed, to this deployment's receiver -- at least once |
| `inbound` | a signed `POST /connectors/<name>` | starts a run of one installed definition as the agent bound to it, the request body as the run's input |
| `scheduled` | its interval | starts a run of one installed definition as the agent bound to it, with a fixed input |

## The file

`projects/<slug>/connectors/<name>.yaml`, beside `workflows/`. Immutable per
`(name, version)`: fix one forward by publishing a new version.

```yaml
schema_version: 1
name: note-embedded            # ^[a-z][a-z0-9-]{0,62}$
version: 1
description: >-
  What the receiver does with this event.
kind: outbound
event: note_embedding.set@1    # name@version -- an event whose shape changed is a new version
retry:
  max: 2                       # 0..10; attempts = max + 1
  backoff_seconds: 2           # 1..3600, fixed
```

```yaml
kind: inbound
workflow: notes-inbox@1        # a definition this set installs
body:
  members:
    title:   {type: string, required: true, max_length: 200}
    content: {type: string, required: true, max_length: 4000}
```

```yaml
kind: scheduled
workflow: notes-digest@1
schedule:
  every_seconds: 60            # 60..86400
input:
  limit: 1                     # literals only: a schedule has no request
```

**An inbound body is a closed subset, not JSON Schema** (ADR 0237): at most 16
members, each a `string` (with `max_length`), an `integer` (with `minimum` and
`maximum`) or a `boolean`; no nesting and no member the file does not name.
The body IS the run's input, so the compiler checks it in both directions -- a
member the definition never reads as `{{input.<m>}}` is refused, and so is an
input the definition reads that the body does not declare -- and every member
is `required: true`, because the worker has no default to resolve an absent
key to (D1831). A scheduled `input` gives exactly the keys the definition reads,
as literals.

**The file never names an endpoint.** A file is shared by every deployment of
its set; the endpoint is the deployment's (next section).

```bash
bin/connector.sh init --kind outbound|inbound|scheduled --project project.yaml [--name NAME]
bin/connector.sh validate --project project.yaml [--file PATH]
```

`init` prints a skeleton derived from your set's own definitions that compiles
as printed; `validate` compiles every connector against your lock and your
definitions and exits 5 naming the file and the member. Neither needs a
deployment.

## The manifest

```yaml
schema_version: 7
connectors:
  enabled: true
  endpoints:
    note-embedded: https://receiver.example.com/hooks/apg
```

`connectors.enabled` turns on the **facility**: one secret,
`connector_signing_key`, which every connector's key is derived from. A
project that leaves it off owes nothing new and installs no connector. An
endpoint is `http` or `https`, a host, an optional port and path -- no user,
password, query or fragment, so it cannot carry a credential -- keyed by the
name of an OUTBOUND connector of the set. The deploy's step 6e installs every
connector and reports, never printing an endpoint, an outbound connector the
manifest gives none (`enable` will refuse it) and an endpoint that names no
outbound connector (installed nowhere).

## The signature

One scheme, both directions (ADR 0237). Three headers:

| Header | Value |
|---|---|
| `X-Apg-Delivery` | a uuid, canonical lowercase -- the delivery's identity, and inside the signature |
| `X-Apg-Event` | `<name>@<version>` -- outbound only |
| `X-Apg-Signature` | `t=<unix seconds>,v1=<64 lowercase hex>` |

The signed bytes are the time, a dot, the delivery id, a dot, then the raw
body exactly as sent:

```
<t>.<delivery id>.<body bytes>
```

`v1` is HMAC-SHA256 of those bytes under **the connector's key** (64 hex
characters, 32 bytes). A request is accepted within **300 seconds** of `t`,
either side, so a sender's clock matters: a drifted clock is refused exactly
as a forger is. Because the delivery id is signed, a captured request cannot
be replayed under a fresh id; replayed under the same id, it meets the receipt
(`delivery_replayed`).

Computing one with nothing but `openssl` -- this vector is the one the
product's own proofs pin:

```bash
KEY=000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
T=1727600000
DELIVERY=7f1c1d6e-0000-4000-8000-000000000034
printf '%s' '{"note_id":"00000000-0000-4000-8000-000000000001"}' > body.json
{ printf '%s.%s.' "$T" "$DELIVERY"; cat body.json; } \
  | openssl dgst -sha256 -mac HMAC -macopt "hexkey:$KEY"
# SHA2-256(stdin)= 3c87822a243911edc8870359fd62616a6867de84986eef164eb028888a257aba
```

Sign the bytes you send and send the bytes you signed: re-serialising the body
after signing it changes it.

### The key

Each connector's key is derived from the project's master and the connector's
NAME, so a receiver holding one connector's key can sign or verify for that
connector and no other. An operator writes it for a sender, as root, on the
host:

```bash
sudo bin/connector.sh key --project project.yaml --name notes-inbox --output /root/notes-inbox.key
```

It is written to a NEW file, mode 0600, and never printed. Hand it over out of
band. Replacing `APG_CONNECTOR_SIGNING_KEY` at the provider and redeploying
changes **every** connector's key of that project at once (operator guide
§18).

## Inbound

`POST https://<domain>/api/app/connectors/<name>`, with no bearer token -- the
signature is the credential. The order is fixed, and nothing reaches the
database until the signature holds:

| Answer | When |
|---|---|
| `404 {"error":"no_such_connector"}` | the name is not a connector name, the project has no connectors facility, or no INBOUND connector has that name |
| `413 {"error":"body_too_large"}` | the body is above 16 KiB |
| `401 {"error":"signature_invalid"}` | ANY signature failure -- a missing or malformed header, a non-canonical delivery id, a time outside the window, the wrong key, the wrong delivery id, a changed body. One answer for every cause |
| `400 {"error":"malformed_request"}` | signed, and not a JSON object (or a duplicate member) |
| `422 {"error":"body_not_permitted","reason":…,"member":…}` | outside the declaration: `reason` is `missing`, `type`, `too_long`, `out_of_range` or `unexpected_member`; `member` names a DECLARED member, or is null |
| `409 {"error":"delivery_replayed"}` | this delivery id was accepted before; a retry starts nothing |
| `409 {"error":"connector_disabled"}` | not enabled, or disabled since |
| `409 {"error":"agent_scopes_differ"}` / `agent_not_active` | the bound agent's stored scopes no longer EQUAL the definition's, or it was revoked |
| `202 {"run_id":…,"status":"queued"}` | a run of the definition, as the bound agent, with the body as its input |

**Retry on a 5xx or a timeout with the SAME delivery id**: an accepted id is
never accepted twice, and a refused enqueue leaves no receipt. The edge's own
limits apply before the service sees anything: 16 KiB per body and 20
requests per second per source (burst 40).

## Outbound

When your SQL emits an event -- a definer function in your set calling
`app.emit_event(name, version, payload)` (ADR 0235) -- one delivery is recorded
for each ENABLED outbound connector with an endpoint that subscribes to it.
Nothing is recorded when nothing listens.

The worker (the loop inside `auth`) POSTs each delivery with the three headers
above and a canonical body -- sorted keys, no whitespace -- of `delivery_id`,
`emitted_at`, `event`, `event_id`, `payload` and `version`. A `2xx` is
`delivered`. Anything else -- another status, a refused
connection, a timeout (10 s), a TLS or DNS failure -- is retried after
`backoff_seconds` until `max + 1` attempts, then `dead` with a fixed token:
`http_<code>`, `timeout`, `connect_failed`, `tls_failed`, `dns_failed` or
`unknown`. **A redirect is never followed.** On an idle deployment the
spacing is the longer of the backoff and the loop's five-second pause (D1838).

**At least once.** A worker that dies mid-POST re-delivers when its lease
expires, so a receiver **de-duplicates on `X-Apg-Delivery`**. The receiver
learns the body and the headers, and nothing else: no bearer, no cookie, no
project credential (THR-DELIVERY).

A disabled connector's pending deliveries are held, not sent, until it is
enabled again.

## Enabling, and the status

Three routes for a HUMAN administrator, and `bin/connector.sh`'s three verbs
over them with `APG_API_TOKEN`:

```bash
bin/connector.sh status  --project-outputs outputs.json [--dead-limit N]
bin/connector.sh enable  --name notes-inbox --confirm notes-inbox --agent AGENT_ID --project-outputs outputs.json
bin/connector.sh disable --name notes-inbox --confirm notes-inbox --project-outputs outputs.json
```

`status` needs `admin_connectors:read`; `enable` and `disable` need
`admin_connectors:write`. Both are in the project administrator's ceiling and
**no administrator holds either until an operator grants it**. An agent token
is refused by all three.

**Binding.** An inbound or scheduled connector starts runs AS the agent named
at `enable`, which must be active, bound to no other connector, and hold
**exactly** its definition's scopes -- no fewer, and no more (`agent_scopes_differ`).
Create a dedicated agent for each. An outbound connector acts as nobody: name
no agent (`agent_not_needed`), and it needs an endpoint (`no_endpoint`).
Enabling a scheduled connector fires it at once, then every `every_seconds`;
missed fires coalesce to one.

**The status document** is printed whole: each connector's kind, version and
binding as it stands NOW (`ok`, `unbound`, `agent_not_active`,
`agent_scopes_differ`, or `not_applicable`), whether an endpoint is declared,
who enabled or disabled it, the pending, delivered and dead counts, the oldest
pending delivery's age, the last error token, the receipts, and up to 20 dead
letters by event and token. **Never an endpoint, a payload or a key.**

## What is not here

| Not here | Why |
|---|---|
| Redelivering a dead letter | a human write to the outbox, which needs its own scope and audit story; dead letters are visible, not replayable (D1798) |
| A `test` verb | a real delivery is not a test, and one that did not deliver would test nothing (D1797); `validate` compiles, `workflow dry-run` rehearses the definition, and a real signed request is the check |
| Events from anywhere but your own SQL | an event reaches only its own project |
| Pruning events, deliveries and receipts | the retention story an operator horizon would answer (ADR 0213's shape) |
| A per-connector key rotation | one master per project (D1784); rotating it rotates every connector's key |

The operator's half -- enabling the facility, handing a key over, the doctor's
clause, the rehearsal and the drill -- is `docs/operator-guide.md` §18.
