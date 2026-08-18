# 0107 — The addressing style is `path`, because it is the only invariant one

Status: accepted
Date: 2026-08-18
Session: 7, Run 5
Affects: STO-URL-001

## Context

The session plan says the R2 client uses "one addressing style **frozen after
being proved**". Run 5 measured it against a real bucket before writing the
client, and the measurement says the instruction cannot be carried out the way
it is written.

**Both styles work.** Against `apg-session7-r2-probe`, a presigned PUT was
issued under each style and the bytes were actually sent — not merely signed:

| `s3.addressing_style` | emitted host | shape | presigned PUT |
|---|---|---|---|
| `virtual` | `apg-session7-r2-probe.<ACCOUNT>.r2.cloudflarestorage.com` | virtual | **200** |
| `path` | `<ACCOUNT>.r2.cloudflarestorage.com` | path | **200** |
| `auto` | `<ACCOUNT>.r2.cloudflarestorage.com` | path | **200** |

So the choice is not about which one R2 accepts. It is about which one the
product can *guarantee it emits*, and that is where the measurement turned.

**Setting the config key does not freeze the style.** The same client
configuration, `addressing_style: "virtual"`, produces a different URL shape
depending on the bucket name:

```
bucket apg-session7-r2-probe   ->  apg-session7-r2-probe.<ACCOUNT>.r2...   virtual
bucket apg.dotted.probe        ->  <ACCOUNT>.r2.cloudflarestorage.com      PATH
```

botocore detects that a dotted name is not usable as a TLS hostname label and
silently falls back to path style. Nothing raises, nothing warns, and the
returned URL is perfectly valid — it is simply not the shape that was
configured. An earlier arm of the same rig had already shown the pair can differ
for a second reason: against a non-R2 endpoint, `virtual` also presigned a
path-style URL.

**The deciding input is operator-supplied.** ADR 0105 says an explicit
`storage.bucket` override is used **verbatim**, and
`schemas/project.schema.json` bounds it only at 3–63 characters. A dotted bucket
name is therefore a legal manifest value, which means the shape of every
presigned URL the product issues is a function of a field an operator may set
without knowing it is deciding anything.

That is this repository's defect pattern exactly: *a value that looked
configured and was not*. `PGRST_DB_PRE_REQUEST` (D192) was set by a rig and never
by the product; here a key is set by the product and honoured only for some
inputs. Both pass review by being present.

## Decision

**Freeze `path`, explicitly, and never `auto`.**

```python
config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, ...)
```

`path` is the only style botocore will always actually produce: it has no
hostname constraint to fall back from, so the configured value and the emitted
value are the same value for every bucket name the schema admits.

`auto` resolves to `path` here today and is still refused, because `auto` is a
*behaviour* rather than a choice. It is decided by botocore's version and by the
bucket name, and a lock that pins a version is not a substitute for stating the
intent — the same reason `versions.in.yaml` pins `botocore` even though `boto3`
resolves it to the same number today.

## Consequences

The bucket name appears in the URL **path** rather than the hostname. Two
downstream effects, both wanted:

A dotted or otherwise DNS-hostile `storage.bucket` override now behaves
identically to every other bucket name, instead of quietly changing the URL
shape. The override stays as permissive as ADR 0105 made it deliberately.

A CORS policy or a debugging session reads one hostname for every project and
every bucket. Under virtual addressing the origin of a presigned URL varies per
bucket, which Run 7's edge CORS pair would have had to account for.

**A test asserts the emitted shape, not the configured key.** Asserting
`config.s3["addressing_style"] == "path"` would pass in exactly the case this
ADR exists to prevent — it is the assertion that cannot fail (D173, D260). The
test presigns against a dotted bucket name and a plain one and asserts both
URLs carry the account host with the bucket in the path.

## What was not measured

Whether R2 would accept a virtual-hosted request for a *dotted* bucket if one
were somehow issued. It cannot be issued: botocore declines to build it, so the
question has no reachable arm. No dotted bucket was created — the probe fails
before any bucket is touched — and this is recorded as an unmeasured boundary
rather than as a fact about R2's certificates.
