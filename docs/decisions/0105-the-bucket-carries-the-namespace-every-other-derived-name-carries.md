# 0105 — The bucket carries the namespace every other derived name carries

Status: accepted
Date: 2026-08-16
Session: 7, Run 3
Amends: [0102](0102-the-object-key-is-one-derivation-over-the-prefix-naming-owns.md)
Affects: STO-KEY-001, DEP-ISO-002

## Context

`naming.py` is the single authority for every derived name in this project
(ADR 0002), and every one of them carries a namespace:

```
traefik routers      apg-alpha-dev-app, apg-alpha-dev-docs
traefik middlewares  apg-alpha-dev-api-buffering, apg-alpha-dev-docs-auth
database roles       apg_alpha_dev_storage_service
R2 bucket            alpha-dev            <- the sole exception
```

D330 examined the bucket derivation in Run 1 and concluded nothing needed
fixing. That conclusion was reached by **reading the deriver** — which was the
right method for the question being asked, and answered a different question from
this one. The prediction under test was whether the manifest's `bucket` was a
*second* derivation competing with `naming`'s. It was not; it is an override of
it. Nobody asked whether the name the derivation produces is a good name.

Run 3 listed a real Cloudflare account, read-only. It holds six buckets:
`cursor-clone-files`, `items`, `note-app-marshal-images`, `photos`, `pictures`,
`vector-attachments`. None collides with `alpha-dev` or `beta-dev` today.

**But a bucket's collision domain is the entire account**, unique per account and
jurisdiction — and `alpha-dev` is precisely the kind of name a human creates for
something unrelated in an account that already contains `items` and `photos`.
Every other name this project derives is unmistakably ours; the one that shares a
namespace with a third party's console is the one that is not.

The consequence is bounded but real. §4's safety plan already says a same-named
bucket is **not** ownership proof: the bootstrap reads back account, name,
jurisdiction, creation time and public-access state and stops for operator review
when continuity cannot be proved, and it never deletes a bucket as rollback. So a
collision is a hard stop rather than data loss. It is an operational trap, not a
security hole.

**What makes it worth an ADR is the asymmetry in cost.** No bucket exists yet, so
changing the derivation now costs a re-render. R2 has no rename, so changing it
after Run 5 creates one means copying every object into a new bucket and
repointing a live deployment.

## Decision

**The derived bucket name is `apg-{project_key}`.** `apg-alpha-dev`,
`apg-beta-dev`.

**An explicit `storage.bucket` in the manifest is used verbatim and is not
prefixed.** The override exists so an operator can point at a bucket named by a
convention that is not ours, and prefixing it would defeat the only reason it is
there. A collision on an overridden name is the operator's to resolve — which is
what an override means — and the bootstrap's refusal to adopt a bucket it did not
create still applies.

**The object-key prefix is unchanged and stays `objects/{project_key}/`.** It
lives inside a bucket this project already owns, so there is no namespace to
share and nothing to collide with. Prefixing it would be symmetry for its own
sake, and it would change every object key for no reason.

## Consequences

**`project.example.yaml` stops declaring `bucket` and `prefix`.** Until now both
fixtures declared exactly what the derivation produced, so **no fixture exercised
the derivation at all** — this change would have left the entire suite green.
That is D332's rule arriving for a third time in one session: *two fixtures that
agree on a value cannot prove the value is read*, and its sharper form here is
that a fixture which restates a default cannot prove the default. Alpha now takes
both derived names and alpine overrides both, so the pair covers both paths.

**This is the second finding in this session that came from leaving the
repository.** D333 was found by running a code path nobody had run; this was
found by listing an account nobody had listed. Both were invisible to a suite
that was green, and both were about a value that looked settled.

**The operator guide's instruction is unchanged and was already right.** It tells
the operator to *read* the bucket names out of `naming` rather than type them,
so it produces the new names with no edit. An instruction that had spelled the
names would now be wrong.

## Alternatives considered

**Leave it and rely on the ownership stop.** Rejected on the cost asymmetry
above, not on the safety of the stop — the stop is correct and stays. The
objection is that it is reachable by an unrelated human action in a shared
account, and that recovering from it means choosing a different name through
`storage.bucket` anyway. Doing that once, deliberately, in the derivation is
cheaper than doing it under time pressure during a deploy.

**Require a dedicated Cloudflare account per deployment.** Rejected because it
makes the operator guide describe a setup that demonstrably does not exist: the
account this was measured against holds six unrelated buckets, and a prerequisite
nobody meets is a prerequisite nobody reads.

**Namespace the override too.** Rejected: it removes the override's only purpose
and makes `bucket: my-existing-bucket` silently mean something else, which is a
manifest field that lies about what it does.

**Namespace the object-key prefix as well.** Rejected as above — the prefix is
scoped by a bucket this project owns, so the change would buy nothing and would
alter every object key.
