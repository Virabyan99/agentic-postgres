# 0054 — A secret may be consumed by the root plane, and says so

Status: accepted
Date: 2026-08-11
Session: 5, Run 3
Extends: [0010](0010-secret-materialization.md), [0036](0036-the-provider-bootstrap-seeds-what-the-contract-declares.md)
Affects: SEC-BOOT-001, SEC-DOCS-001, DEP-SEC-001

## Context

Session 5 introduces two values that no container may hold.

**The bootstrap issuer's private signing key.** ADR 0051 says it is "mounted into
no service, printed by no command, and passed as no argument". PostgREST receives
a verification-only JWKS derived from it; nothing receives the key itself.

**The documentation credential.** D140 found the problem: the runbook adds
`docs_basic_auth_password` to `secrets.required.yaml`, and the contract has no
shape for it. `schemas/secret-contract.schema.json` requires `consumers` with
`minItems: 1`, and `tests/contract/test_secret_contract.py` cross-checks every
consumer against a Compose service and that service's `user:`. **Traefik is not a
project Compose service** — it is the shared edge stack in
`infra/edge/compose.yaml` — and the documentation service must never receive the
cleartext, which is the entire point of stripping the header before it reaches
that container. There is no service to name.

Both values are read by root on the host: one by the tooling that signs tokens,
one by the deploy that derives a hash into the edge's dynamic configuration.

Three options were weighed in D140. Generating the value in the deploy and never
sending it to the provider is the cheapest, and it breaks "secret material is
published as an immutable generation" for exactly one value. Naming the
documentation service as consumer is refused outright: it materializes the
cleartext into the one container that must not have it.

## Decision

**A consumer declares its `plane`, and `root` is a plane.**

- `plane: compose` names a Compose service, is cross-checked against that
  service's `user:`, and may not be owned by root — a root-owned file mounted
  into a container that drops privileges is unreadable by the process that needs
  it, which is the rule that has been in the contract since Session 2.
- `plane: root` names **no service**, is materialized into `_root/` inside the
  generation, must be owned `0:0` at mode `0400`, and is granted to no container.
  `_root` is a directory name no Compose service can have — the service pattern
  admits no underscore — so a root-plane file and a service's directory cannot
  collide by construction rather than by convention.

`plane` is **required on every consumer**, including the ten that existed before
this decision. The same reasoning as `one_time_initialization`: a new consumer
has to state which kind it is, and a default is how a value ends up in the wrong
plane because nobody wrote the field.

The Compose grant renderer emits nothing for a root-plane consumer — no
`secrets:` entry, no service grant, no mount — and a contract test asserts the
absence rather than trusting it.

## Consequences

**The documentation credential has somewhere legal to live.** It is fetched from
the provider like every other secret, materialized root-only, and the deploy
derives the edge's `usersFile` hash from it. The cleartext reaches the edge
plane's configuration directory as a hash and reaches the documentation container
not at all.

**`migration_user_password`'s bootstrap reader is deliberately *not* migrated to
this shape**, and the Session 5 plan's aside that this decision would give it
"somewhere honest to live" is wrong. That reader is root on the host and reads
*dbmate's already-materialized copy*; declaring a root-plane consumer for it
would materialize a **second copy** of one credential — which is the thing that
file's own comment refuses, in those words, twice. A root-plane consumer is a
materialization target for a value no container may hold, not a way to record
that root can read a file root can already read.

**Root ownership is now representable, and only here.** The refusal of `uid: 0`
that has guarded the compose plane since Session 2 is unchanged for that plane
and inverted for this one: a root-plane consumer that declared a non-root uid
would be a file no root-only reader is entitled to assume, and it is refused.

**The generation manifest carries the plane too.** It is rewritten on every
materialization, so the cost is a schema field rather than a migration, and a
manifest that recorded a root-plane file as though a service held it would
describe a grant surface that does not exist.

## Alternatives considered

**Generate the two values in the deploy and skip the provider.** Rejected: it
makes two values invisible to rotation, to the generation manifest, and to the
"secret material is published as an immutable generation" property that every
other credential has. It also puts key generation on a path that runs on every
deploy rather than on the path that runs when a project is created.

**Name the documentation service as the consumer.** Refused, as D140 says. It
materializes the cleartext into the one container the whole design keeps it away
from, in order to satisfy a schema requirement.

**Relax `consumers` to `minItems: 0`.** Rejected, and it was tempting: a secret
with no consumers is materialized nowhere, which is nearly what a root-plane
secret wants. It is not the same thing — a value nothing consumes is a value
nothing *writes*, and the root reader needs a file at a path it can name. It
would also delete the property that every declared secret has a stated reader.
