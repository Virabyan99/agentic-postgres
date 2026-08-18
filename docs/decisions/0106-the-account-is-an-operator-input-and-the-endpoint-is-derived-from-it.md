# 0106 — The account is an operator input, and the endpoint is derived from it

Status: accepted
Date: 2026-08-18
Session: 7, Run 5
Extends: [0002](0002-outputs-json-is-the-single-authority-for-derived-names.md), [0105](0105-the-bucket-carries-the-namespace-every-other-derived-name-carries.md)
Affects: STO-URL-001, DEP-ISO-002

## Context

Runs 2, 3 and 4 built the storage plane's identity, its migration and its
database role, and Run 5 set out to write the client. It cannot: **nothing in
this repository says where the bucket is.**

The `storage` Compose service is handed eight `STORAGE_*` variables — bucket,
prefix, the three bounds, the pool size, the memory limit, the role name — and
two mounted credential files. There is no endpoint and no account identifier
anywhere:

```
compose.yaml                    8 STORAGE_* variables, no endpoint
rendering.py                    the same 8, derived
naming.py                       storage_bucket_name, storage_object_prefix
schemas/project.schema.json     storage: additionalProperties: false
```

The last line is the one that makes this a decision rather than an omission to
patch. The `storage` block refuses unknown members, so an operator **cannot**
supply an account id even by hand. §3 of the session plan lists "Account id,
jurisdiction" as operator input, and four runs of work went past that row
without anything implementing it.

This is D276's shape from the other side. There, a declaration said the JWKS was
derived from a key and nothing derived it. Here, a feasibility table says a value
is an operator input and nothing accepts it. **A plan's input table is not an
interface; grep for the reader.**

### What the endpoint actually is

Measured in Run 5 against a real bucket, not read from the S3 documentation:

```
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

The account id is a 32-character hex string. A bucket created in a jurisdiction
is reachable only through that jurisdiction's own endpoint
(`https://<ACCOUNT_ID>.<JURISDICTION>.r2.cloudflarestorage.com`), and the probe
bucket this run measured against reports `jurisdiction: default`.

## Decision

**The account id and the jurisdiction are manifest inputs. The endpoint is
derived from them by `naming.py`, once, and handed to the container.**

```
storage.account_id      required when storage.enabled, 32 lowercase hex
storage.jurisdiction    default | eu | fedramp, defaulting to "default"

naming.storage_endpoint_url(account_id, jurisdiction) -> str
STORAGE_ENDPOINT        rendered from it, refused if empty
```

Three properties, and each is a rule this project already holds:

**One derivation.** The endpoint is assembled in `naming.py` and nowhere else
(ADR 0002). The container receives a URL, not two fragments and a format string
— a second assembly site inside the image would be a second authority for a
value the deploy already knows, which is what `routes.docs` cost in Session 5
(D177) when two derivations of one path disagreed and the copy commented as
"kept in step" was the one that had not drifted.

**A manifest field, not a secret.** An account id is an identifier, not a
credential: it appears in the endpoint hostname of every request and in the
dashboard URL. Declaring it in `secrets.required.yaml` would put a
non-credential through materialization, per-consumer copies and generation
rotation — machinery that exists to make "one service cannot read another's
credential" a filesystem property, spent on a value that is not one. It would
also make the endpoint unresolvable at `--render-only` time, which must keep
working with no host and no root.

**Not published in `outputs.json`.** This is the part with a genuine
alternative, so it is argued rather than assumed. `outputs.json` publishes what
the deployment *exposes* — the routes a client dials, the database endpoints a
tool connects to. The R2 endpoint is the opposite direction: it is where one
container dials **out**, like `APG_DATABASE_HOST`, which is likewise absent.
Publishing it would put an account-identifying string into a document that is
read by clients and committed in fixtures, in exchange for no consumer that
needs it. If a consumer ever does, that is an outputs version bump with a
reason, and adding a field is cheaper than unpublishing one.

## Consequences

`storage.account_id` is **required when storage is enabled**, so a manifest that
turns storage on without one is refused at validation rather than at the first
provider call. The refusal names the field and the operator guide's §2, where the
account id is already documented — it was written into that guide in Run 2, one
run before anything could read it.

**The two example manifests disagree about it, in this commit** — alpha carries
one account id and omits `jurisdiction`; alpine carries a different account id
and names `eu`. So the pair covers the branch that inserts a jurisdiction label
and the branch that does not, and a renderer ignoring either input fails one of
them.

That the fixtures cover both branches is D332 for the fourth time, and the rule
it produced is why it is done in the same commit rather than a run later: when
you add a published field, make the fixtures disagree about it. Two fixtures
that agree on a value cannot prove the value is read, and one that restates a
default cannot prove the default — which is why alpha omits `jurisdiction`
entirely instead of writing `default`. Run 2 hit this on four of eight storage
variables one run after recording it.

An honest note about how this section was written, because it bears on the rule
above. Its first draft said both example manifests kept storage disabled and
that the tests would therefore build their own fixtures. That was an assumption
about the fixtures, not a reading of them: both enable storage, and the full
suite said so by failing sixty-nine tests the moment `account_id` became
required. The unit tests that construct their own pair were kept anyway — they
cover the malformed and disabled cases the manifests cannot — but the manifests
are the fixtures that matter, and the paragraph asserting otherwise was exactly
the "value that looked checked and was not" this repository keeps producing,
committed into an ADR.

The jurisdiction enum is closed at the three Cloudflare documents today. That is
a value read from vendor documentation and it is recorded as one: only `default`
has been measured, because only `default` is what the probe bucket is. A
jurisdiction this project has never dialled is a name in a list, and the schema
says so.

## Alternatives rejected

**A `host.yaml` field.** The account is a property of the Cloudflare
organisation, not of the VPS, and `host.yaml` describes the machine. It would
also force both projects onto one account permanently, when the per-project
token isolation the operator guide already requires suggests the account may not
always be shared.

**Deriving the endpoint inside the image from two environment variables.**
Cheaper by one function and wrong by ADR 0002. The image would then know the URL
format, and a jurisdiction change would need a rebuild rather than a manifest
edit.

**A fourth secret, `r2_account_id`.** Rejected above, and for the reason ADR
0103 gives about `origin`: the contract should be able to state what a value
*is*. An account id is not a credential and calling it one makes the contract
less true, not more careful.
