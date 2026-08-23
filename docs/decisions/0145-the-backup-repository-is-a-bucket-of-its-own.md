# 0145 — The backup repository is a bucket of its own, with its own credential and its own key

Status: accepted
Date: 2026-08-23
Session: 10, Run 2

Affects: REC-EVID-001, SEC-SECRET-001, THR-BACKUP-COMPROMISE, D512, D521,
ADR 0105, ADR 0106, `src/agentic_postgres/naming.py`,
`src/agentic_postgres/config.py`, `schemas/project.schema.json`,
`secrets.required.yaml`

## Context

`docs/source-specification.md` §12.2 asks for two things and offers a fallback
for one of them: *"Application services must not possess backup-bucket
credentials"*, and backup data *"must use a separate bucket or, at minimum,
separate credentials and a separate prefix that application services cannot
access."*

The repository already derives `backup_repository_prefix` —
`pgbackrest/<key>/` — and has since Session 1. Taking the fallback would cost
nothing: point pgBackRest at the existing `storage.bucket` under that prefix,
issue a second token, and be done.

The reason not to is what a token can actually be scoped to. R2 scopes an API
token to buckets. Prefix-scoping is expressible in a policy but is not what the
Object Read & Write token this project already issues does, and ADR 0110 puts
bucket administration out of band precisely because nothing here creates or
configures buckets. So under the fallback, "the storage service cannot reach the
backup repository" would be a sentence in an operations document with no
executable check behind it — and `THR-BACKUP-COMPROMISE`'s stated control is
*"credential-scope checks assert application services cannot reach the backup
bucket."*

There is also a measured precedent for what an unscoped name costs. D339 found
`storage_bucket_name` returning a bare project key into an account already
holding six unrelated buckets, and ADR 0105 namespaced it — noting that it
*"could not have been changed after a bucket held objects: R2 has no rename."*
A repository is the one store in this system that is worthless if it has to be
recreated.

## Decision

**The pgBackRest repository lives in its own R2 bucket, reached with its own
credential, encrypted with a key stored separately from that credential.**

- `naming.backup_bucket_name(key, override)` derives `apg-<key>-backup`.
  **ADR 0105 is applied, not restated**: the derived name carries the `apg-`
  namespace, and an explicit `backup.bucket` is used verbatim and unprefixed.
- `backup.account_id` is a manifest field of its own, so a repository may live
  in a different Cloudflare account from application objects. Nothing requires
  the two to match and nothing requires them to differ.
- The endpoint is derived by **`naming.storage_endpoint_url`** — the same
  function storage uses, not a second one (ADR 0002, ADR 0106) — and handed to
  the container finished.
- Three secrets, landing in Run 3: `backup_r2_access_key_id` and
  `backup_r2_secret_access_key` (`origin: operator_supplied`, provider path
  `/backup`) and `pgbackrest_repo_cipher_pass` (`origin: generated`).
- **No application service is granted any of the three**, and the backup
  credential is granted to no service that holds `r2_access_key_id`.

## Consequences

**The isolation becomes a measurement.** `HeadBucket` with the storage token
against the backup bucket, and with the backup token against the storage
bucket, are two requests with an expected status each. D344 already measured the
neighbouring trap — a bucket-scoped token answers **403, not 404**, for a bucket
that does not exist — so the check must be run in both directions against
buckets known to exist, or it passes for the wrong reason.

**The operator creates one more bucket and one more token, out of band, per
project.** That is a real cost on every host trip and it is paid once per
project. It is the same shape as Session 7's storage credential and the operator
guide inherits that section rather than inventing one.

**Encryption is ours, not the provider's.** `repo1-cipher-type=aes-256-cbc` with
a generated pass phrase means a reader of the bucket holds ciphertext. The
cipher pass is a separate secret from the credential so that leaking one does
not yield the other — which is the only part of `THR-BACKUP-COMPROMISE` this
session can actually control.

**What this does NOT buy** is a disaster-recovery boundary. Both buckets can sit
in one Cloudflare account, and an account-level compromise defeats the
separation entirely. `docs/threat-model.md` says so already and this decision
does not change it; the operations documentation must keep saying so.

**A bucket cannot be renamed.** Getting the derived name wrong is expensive
after the first backup, which is why the name is derived rather than typed and
why `evidence.ISOLATED_FIELDS` compares it across projects before any cluster
exists.

## Alternatives considered

**One bucket, two prefixes, two tokens** — the specification's own fallback.
Rejected because the isolation claim would rest on prefix scoping that this
project does not issue and cannot check, turning a measurable 403 into a policy
sentence. Recorded rather than dismissed: it is the correct answer for a
deployment whose provider scopes tokens to prefixes, and nothing in the
repository would need to change but the derivation and the token.

**One bucket, one token, encryption as the only boundary.** Rejected: it makes
the cipher pass the single thing standing between an application-service
compromise and every historical copy of the database, and that pass has to be
readable by the Postgres container anyway.

**A separate Cloudflare account for backups.** Not chosen and not refused —
`backup.account_id` exists precisely so this is a manifest change rather than a
code change. It is the only option that would make backups survive an
account-level compromise, and `docs/threat-model.md` lists it as post-MVP.
