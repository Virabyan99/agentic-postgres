# 0110 — The bucket-administering credential is not an S3 credential

Status: accepted
Date: 2026-08-18
Session: 7, Run 8
Affects: D347, ADR 0105, ADR 0106, ADR 0107, `bin/storage-admin.sh`,
`docs/session-07-operator-guide.md`, section 4 of the Session 7 plan

## Context

Section 3 of the session plan assumes one bucket-scoped **Object Read & Write**
token does everything, and section 4 has the *bootstrap* creating the bucket.
Those cannot both be true, and Run 5 measured which one is wrong (**D347**):

| operation, with the runtime's Object R&W token | result |
|---|---|
| `CreateBucket` (S3 API) | **403 AccessDenied** |
| `ListBuckets` (S3 API) | **403** |
| `HeadBucket` on an unrelated bucket in the same account | **403** |
| the R2 REST API, same token | refused outright, error `10000` |
| creating a bucket through the **Cloudflare REST API** | **succeeded** — it is how the probe bucket existed |

So a second credential is needed. Run 5 left open **which kind**: an R2 *Admin*
S3 token used with `CreateBucket`, or a Cloudflare API token used against the
REST API. It could not answer, and said so honestly: the token issued as the
Admin arm turned out to behave identically to the first — same refusals, same
scope — so the pair discriminated nothing and the arm was recorded
**uninformative** rather than reported from the arm that did run.

That leaves the question open on capability grounds. It is decided here on
different grounds.

## Decision

**The credential that administers a bucket is a Cloudflare API token used
against the Cloudflare REST API, it is held by a human, and no process in this
repository holds it.**

Three consequences, and the third is the one that matters:

1. Creating the bucket, reading its identity back, and issuing or revoking an
   R2 token are steps in `docs/session-07-operator-guide.md`, performed by a
   person. They are three of section 4's five irreversible operations.
2. `bin/storage-admin.sh` has **no bucket-administering verb**. Not "has one
   that refuses" — has none.
3. The secret contract gains nothing. There is no new declaration, no new
   provider path, and nothing to materialize, because there is no consumer.

## Why this rather than an R2 Admin S3 token

**Because a second S3 credential would be interchangeable with the runtime's at
every call site.** The runtime reaches R2 through exactly one object,
`R2Adapter`, built by `build_client` from a `StorageConfig`. An admin S3
credential would be the same protocol, the same endpoint, the same botocore
client and the same four method names. The only thing keeping the two apart
would be which file a given process happened to read — a discipline, enforced by
nobody.

The whole shape of this system's credential separation is the opposite of that.
Per-consumer materialization is what makes "the auth service cannot read the R2
credential" a **filesystem property** rather than a rule somebody keeps; the
`storage` consumer is granted no signing key, so `APG_SIGNING_KEY_FILE` is simply
absent from its environment and there is nothing on disk to read. A capability
this project wants to withhold, it withholds by making it unreachable.

A Cloudflare API token against the REST API is unreachable in that sense. It is
a different protocol over a different host, and **the storage image contains no
code that can speak it** — there is no REST client, and
`test_the_service_never_constructs_a_network_jwks_client` refuses any
network-capable module reference anywhere under the service, so adding one is a
test failure rather than a decision somebody makes quietly. Section 8's invariant
*"the runtime credential cannot administer the bucket"* stops being a claim about
a token's scope, which is Cloudflare's to change, and becomes a claim about what
code exists.

**The capability question is left open on purpose, and that is not a gap in this
decision.** Whether an R2 Admin S3 token *can* `CreateBucket` is still
unmeasured. It does not matter: even if it can, the answer above is the same,
because the objection is to the credential being an S3 credential rather than to
its scope. Deciding this on structure means it does not have to wait for a
measurement that would require issuing an account-wide admin token — and passing
one of those through a session is a larger exposure than the two bucket-scoped
tokens Run 5 already had to have revoked by hand.

## Alternatives rejected

**An R2 Admin S3 token, held by the bootstrap.** The interchangeability argument
above. It would also mean the bootstrap holds a credential that can delete every
bucket in the account, at a moment when section 4 item 1 forbids deleting a
bucket even as a rollback.

**A Cloudflare API token held by `bin/storage-admin.sh`.** Structurally better
than the previous option and still rejected, for a plainer reason: the REST
client would be written having never run against Cloudflare. Roughly half of
Session 5's measured claims turned out wrong, and *a value that looked measured
and was not* is this repository's standing defect. A read-back that reports
"continuity proved" from an unexercised client is worse than a human reading the
dashboard, because it looks like evidence.

**Nothing at all — let the bootstrap create the bucket with the runtime token.**
Measured impossible: 403.

## Consequences

Section 4 item 1's read-back — account, name, jurisdiction, creation time,
public-access state — is a step a human performs and records, and the operator
guide says so at the point of the step. It is weaker than an automated check and
it is honest about being weaker.

What the repository *can* check, it does. `bin/storage-admin.sh
verify-credential` asks whether the mounted credential reaches the configured
bucket, by `HeadObject` on a key that does not exist — nothing is written. The
discrimination needs no knowledge of R2's error vocabulary: a credential the
provider accepts gets 404 for an absent key (measured, Run 5), and one it does
not gets something else. **It deliberately does not report which of the
credential and the bucket is wrong**, because a bucket-scoped token cannot tell
"absent" from "not yours" — `HeadBucket` on a nonexistent bucket was measured at
**403, not 404** — and a command that guessed would be inventing a distinction
the provider refuses to make.

Session 8 inherits the same rule: FastMCP is not handed the R2 credential, and it
is not handed a bucket-administering one either, because there is not one to
hand it.
