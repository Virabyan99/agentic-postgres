# 0056 — A consumer declares the format its file is written in

Status: accepted
Date: 2026-08-11
Session: 5, Run 4
Extends: [0010](0010-secret-materialization.md), [0054](0054-a-secret-may-be-consumed-by-the-root-plane.md), [0055](0055-the-contract-declares-what-kind-of-value-a-secret-is.md)
Affects: SEC-SECRET-001, SEC-API-001, DEP-ISO-005

## Context

Every service that holds a database credential in this repository assembles what
it needs from the mounted secret in a shell. PgBouncer's entrypoint writes a
`userlist.txt` and a `.pgpass` into its own tmpfs; dbmate builds a URL at run
time; three of the four client fixtures write a `0600` pgpass. ADR 0034 and D101
are both about doing that rather than putting a password in an environment
variable, and it has worked five times.

**The PostgREST image is distroless.** Measured in Run 1: no shell, no `wget`,
no `curl`, and no `ENTRYPOINT`. There is nothing in the container that can read
one file and write another. The Session 5 plan says "the entrypoint assembles
the database URI in tmpfs at `0600` from the mounted secret file", and there is
no entrypoint that can.

Run 4 measured four ways a password could reach it, with a control that put the
password inline and confirmed the rig was real. All four connect:

| | |
|---|---|
| the password inline in `db-uri` | works, and is exactly what must not happen |
| `PGPASSFILE` with a password-free `db-uri` | works |
| `?passfile=` inside the conninfo | works |
| `db-uri = "@/file"` holding the whole URI | works |

Three of those need a **pgpass-format file** in the container, and the fourth
needs a file holding a URI — which would put a derived role, host and database
name inside an operator-facing value, the thing D60 rejected.

So something must turn a password into a pgpass line, and the only components
that can are the materializer, which writes the provider's bytes verbatim, and a
shell that does not exist.

## Decision

**A consumer declares the `format` its file is written in, and the materializer
writes that format.**

- `raw` — the provider's value, byte for byte. What every existing consumer
  gets, stated rather than assumed.
- `pgpass` — `*:*:*:*:{value}` and a newline. A libpq password file with
  wildcards in all four match fields.

`format` is **required on every consumer**, for the third time and the same
reason as `plane` and `value_kind`: a new consumer states what it gets, and a
default is how a service receives a file in a shape it cannot read.

**Wildcards, deliberately.** The alternative is
`{host}:{port}:{database}:{role}:{value}`, which would put four derived
identifiers into a materialized secret file — a second derivation path for names
`naming.py` already owns, and a file that goes stale when any of them changes,
with `fe_sendauth: no password supplied` as the symptom and the wrong file as
the place to look. The narrowing those four fields would buy is worth nothing
here: the file is mounted into one container, `0400`, owned by the one uid that
process runs as, and that container opens exactly one connection target.

**`pgpass` is refused on anything but a `random_hex` secret.** A pgpass line
holding a PEM is not a thing, and the refusal is at contract load rather than at
the first failed connection.

## Consequences

**PostgREST needs no entrypoint, no config file and no tmpfs for one.** Its whole
configuration is `PGRST_*` environment variables interpolated from `compose.env`
— every one of them a non-secret identifier — and the credential is reached
through `?passfile=` in the conninfo. Measured: the password appears in no
environment variable, no argument (`argv` is literally empty), no label, no log
line and nothing `docker inspect` prints, while the request path answers 200.

**The healthcheck becomes the obvious spelling, and works.** D153 found that
`postgrest --ready` reads its *own* configuration and fails bare. With the
configuration in the environment, its own configuration *is* the service's, so
`["CMD", "postgrest", "--ready"]` exits 0 — measured against a service answering
200, and against `admin-server-host = 127.0.0.1` refusing a peer on the project
network.

**It fails closed, and differently from the pooler.** With an unreadable pgpass,
PostgREST logs `fe_sendauth: no password supplied` and **exits 1**. D101's pooler
logged a permission error and went on listening, refusing every connection while
a port check called it healthy. This one is gone, which is the better failure and
is measured rather than assumed.

**One more field on ten existing consumers.** The diff is wide and the rule is
narrow: nothing that was `raw` changes, and the only entry that is not says so on
its own line.

## Alternatives considered

**Render `postgrest.conf` on the host and mount it.** Rejected: it puts a
cleartext password in a rendered file outside the immutable generation, and the
rendered directory is not where a rotation looks.

**A shared tmpfs volume and an init container that writes the pgpass.** Rejected:
it adds a second image to the service, and a shared mount between two containers
is exactly the property `secrets.required.yaml`'s per-consumer layout exists to
prevent — the file's own comments refuse it twice for other reasons.

**Build a thin image with a shell on top of the PostgREST one.** Rejected. It
adds an unmeasured binary to the one container that faces the public route, to
run three lines of shell, and D147 already declined the same trade for the
healthcheck.

**Store the pgpass line as the secret's value at the provider.** Rejected: the
same value backs the database role, and a role's password is not
`*:*:*:*:hunter2`. The provider would hold a value that only one consumer's
format made sense of, and `value_kind` would be describing a file rather than a
secret.
