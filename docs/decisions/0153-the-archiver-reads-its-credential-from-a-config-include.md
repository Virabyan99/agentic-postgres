# 0153 — The archiver reads its credential from a config include, not from an environment

Status: accepted
Date: 2026-08-25
Session: 10, Run 8b

Affects: D558, D568–D574, ADR 0010, ADR 0056, ADR 0144, ADR 0145, ADR 0151,
`secrets.required.yaml`, `schemas/secret-contract.schema.json`,
`src/agentic_postgres/secrets_contract.py`,
`src/agentic_postgres/secret_override.py`,
`src/agentic_postgres/restore_drill.py`

## Context

D558 is the gap Run 8 found by trying to *use* the archiver rather than by
reading it:

> `build_pgbackrest_conf` omits `repo1-s3-key`, `repo1-s3-key-secret` and
> `repo1-cipher-pass` by construction and its docstring says pgBackRest "reads
> them from the environment" — and **no environment variable, `conf.d` include or
> entrypoint wrapper puts them there.**

The three secrets are declared, materialized, mounted at `/run/secrets/…` owned
by uid 999 at mode 0400, and read by nobody. `compose.yaml`'s `postgres` service
defines four environment variables, none of them pgBackRest's, and
`runtime_override` adds no `environment` key to that service at all.

The consequence is not subtle: **step 6c runs `pgbackrest check` and a check
failure fails the deploy**, so the first deploy of the first project on the host
fails there. That is the design working — loudly, at the right moment — but it
would have been discovered after a trip had been paid for.

**No offline rig before rig 8 could have caught it.** Rigs 4–7 each handed their
own containers a credential of their own, which is ADR 0065/0066's exact warning:
*a proof that reaches the right end state by a route the product does not take
proves the end state is reachable, not that the product reaches it.*

## Decision

### 1. The credential reaches pgBackRest through `/etc/pgbackrest/conf.d`, one option per file

pgBackRest's `config-include-path` defaults to `/etc/pgbackrest/conf.d` and its
own help says the files there "will be concatenated with the pgBackRest
configuration file, resulting in one configuration file". Measured (rig 9),
every arm with a control and every arm with a control **on its own inputs**:

| arm | what | exit |
|---|---|---|
| K1 | one `conf.d` file supplying `repo1-cipher-pass` | **0** |
| K1 control | the same command with no `conf.d` mounted | **37**, `requires option: repo1-cipher-pass` |
| K2 | **three** files, each with its own `[global]` header | **0** |
| K3 | a file with **no** section header | **29** |
| K4 | `conf.d` restating an option the rendered config already sets | **31**, `cannot be set multiple times` |
| K6 | a partial set — the S3 key present, the cipher pass absent | **37**, naming the one that is missing |
| K7 | a `0400` file owned by root, container running as 999 | **41**, `unable to open file … Permission denied` |

K2 is what makes this possible at all: **repeated `[global]` sections across
files concatenate cleanly**, so the contract's rule that it materializes *one
value per file* survives intact. A format that had to pack three values into one
file would be a second parser of a compound value, which ADR 0056 already refused
for the storage pair.

### 2. Not the environment, though the environment works

Rig 8's arm 0 measured that `PGBACKREST_REPO1_CIPHER_PASS` in the environment
works (exit 0 against an encrypted repository; **37** without it), and that
**no `-file` option exists** for any of the three — pgBackRest 2.59.1's only
`-file` options are for TLS and SSH material. So the environment is a real route
and it is refused, for three reasons:

- **It needs an image change.** Compose cannot read a file into a variable, so
  the value would have to be exported by an entrypoint wrapper — and
  `services/postgres/Dockerfile` says in as many words *"No USER line, no
  ENTRYPOINT, no CMD. The base image's entrypoint is what initialises a cluster
  and it is deliberately untouched."* ADR 0144 built that image to add a binary
  and nothing else.
- **It puts the value in `/proc/<pid>/environ`** for every process in the
  container, where a file at `0400` owned by 999 is reachable only by the
  postmaster's uid.
- **It bypasses per-consumer materialization**, which is what makes "the storage
  service cannot reach the backup repository" a filesystem property rather than a
  rule somebody keeps (ADR 0145).

The `conf.d` route needs no image change, keeps the value in a `0400` file, and
travels the grant surface that already exists.

### 3. A third `format`, because the contract anticipated one

`secrets_contract` gains `format: pgbackrest`, beside `raw` and `pgpass`. It
writes:

```
[global]
<option>=<value>
```

The option is **named by the consumer**, in a new `option` field, required when
the format is `pgbackrest` and forbidden otherwise. It is not derived from the
target file's name: deriving a semantic from a filename is how a rename becomes a
silent behaviour change, and this repository derives names *from* meanings rather
than the reverse (ADR 0002).

Both `render_secret` and `recover_secret` learn the format together. They already
raise on an unknown one, and the docstring says why: *"the realistic failure is
not that this is wrong today; it is that a third format arrives and only one of
the two functions learns about it."* This is that third format.

### 4. A newline in the value is refused, and the header is verified on the way back

**K3 is the arm that shapes this, and it is a leak.** A file with no section
header fails with:

```
P00  ERROR: [029]: key/value found outside of section at line 1:
repo1-cipher-pass=rig9-cipher-pass-not-a-real-secret
```

**pgBackRest echoes the value into the error message**, which goes to its console
and to its log file — and for `archive-push` that is the postmaster's stderr, in
the container log. A malformed credential file therefore prints the credential.

So the guard is the same pair `pgpass` already carries, for the same reason:

- `render_secret` **refuses a value containing a line break**, because a newline
  would end the `key=value` line and leave the remainder as a key outside any
  section — which is precisely K3's condition, reached from a value rather than
  from a missing header.
- `recover_secret` **verifies the `[global]` header and the option name** before
  returning anything, and quotes neither the line nor the value when it refuses.

This does not make K3 impossible; it makes the materializer the only writer and
gives it two checks. The residual is recorded in Consequences.

### 5. `conf.d` may only supply options the rendered config omits

K4: an option set in both places is **exit 31**, `cannot be set multiple times` —
not a silent override. That is the good failure, and it constrains the design
rather than threatening it: the rendered `pgbackrest.conf` sets
`repo1-cipher-type` and never the three credential options, and a test asserts
that it never names them.

Stated as a rule because the tempting future edit is to render
`repo1-cipher-pass` "for completeness", which would take every project's archiver
down at once.

### 6. `container_secret_path` becomes the single authority on where a grant lands

The grant surface emitted `target: <target_file>` — a bare basename, which
Compose resolves under `/run/secrets`. `container_secret_path` said the same
thing a second time. Two spellings of one fact, and the `conf.d` route needs them
to disagree.

Measured (rig 9, K8), with a control: **Compose accepts an absolute `target:`**
and the file lands exactly where it says; a relative target lands in
`/run/secrets`, as documented. So `build_secret_override` now emits
`container_secret_path(consumer)` for every consumer, and that function is the
one place that decides.

**And the same arm measured something the existing design was already relying on
without saying so:** Compose warns `secrets 'uid', 'gid' and 'mode' are not
supported, they will be ignored` and passes the **host file's** ownership and
mode through. The contract's `uid: 999, gid: 999, mode: "0400"` are applied by
`materialize-secrets` on the host, which is what actually protects the file — the
grant surface never did. K7 is what a failure of that looks like: exit 41,
loudly, at the first read.

## Consequences

- **The archiver can authenticate.** Nothing in Session 10 could before this, and
  the first deploy of any project would have failed at step 6c.
- `bin/restore-test.py` needs no change. It inherits mounts by *destination* from
  `container_secret_path`, so the drill follows the credential wherever the
  contract puts it — which is what ADR 0151 §2 was built for.
- **The residual on K3 is real and is not closed.** If a credential file ever
  reaches the container without its `[global]` header, pgBackRest prints the
  value. The materializer is the only writer and it has two checks; nothing
  validates the file *at the mount point*, and a future session wanting to close
  this would need pgBackRest to stop quoting the line, which is not ours.
- Three secrets change their container path from `/run/secrets/<name>` to
  `/etc/pgbackrest/conf.d/<nn>-<option>.conf`. Nothing else read them, because
  nothing read them at all — which is the gap this closes.
- Two passing tests in `test_secret_override.py` are **replaced by stricter
  ones**: they asserted the grant target equalled the bare `target_file`, and now
  assert it equals the full container path. That is more than they said before,
  and it is what makes the `conf.d` destination visible to them.

## Alternatives considered

**An entrypoint wrapper exporting `PGBACKREST_*`.** Measured to work, and refused
in §2: an image change, a value in every process's environment, and a route
around per-consumer materialization.

**`--config-include-path=/run/secrets` on every pgBackRest invocation.** Keeps
the files where they are, and puts the flag on `archive_command` — a command line
this repository renders into `compose.env` and which the postmaster runs. It
makes every `.conf` in `/run/secrets` a pgBackRest config, so a future secret
whose target file happens to end in `.conf` becomes archiver configuration.
Refused for that.

**One file with all three options.** Fewer files, and it breaks ADR 0056's rule
that the contract materializes one value per file. K2 measured that three files
work, so there is nothing to trade.

**Deriving the option name from `target_file`.** Refused in §3: a rename would
become a silent behaviour change.

**Repairing this inside Run 8.** Refused at the time and recorded as D558 instead,
because it is an image-or-contract change with its own measurements. It is Run 8b
because the user asked for it before Run 9, and because a Run 9 that proved a
restore against an archiver that cannot authenticate would be proving nothing.
