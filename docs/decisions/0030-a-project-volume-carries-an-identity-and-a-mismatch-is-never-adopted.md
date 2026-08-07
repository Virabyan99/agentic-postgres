# 0030 — A project volume carries an identity, and a mismatch is never adopted

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** DBX-PG-003, DEP-ISO-003

## Context

`POSTGRES_VOLUME_NAME` has been derived and present in `compose.env` since
Session 1. Session 3 is the first session in which it holds anything.

A Docker volume is addressed by name. Names are derived from the project key, so
they are stable — which is the property that makes redeploy work, and also the
property that makes the dangerous case possible. A volume bearing the right name
is not necessarily the right volume: a project key can be reused after a
teardown, two manifests can be edited into agreement, a restored backup can be
attached under a name it did not originally have, and an operator can mistype a
`--project` flag.

In every one of those cases the deployment proceeds happily. Bootstrap finds a
cluster that already exists, skips initialization, applies whatever migrations
are outstanding, and reports success — against somebody else's data.

Session 2 solved the same shape of problem for providers. ADR 0011 records that
provider ownership is tracked by immutable ID and never adopted by name, because
a name is something two things can share and an ID is not. The situation here is
that rule applied to a filesystem instead of an API.

## Decision

**A volume carries an identity, recorded inside the database it holds.**

Before first initialization a candidate project-instance UUID is written to
root-owned state. Bootstrap creates exactly one row in
`app_private.project_identity` carrying it. From that commit forward the UUID is
bound to the volume, and the binding lives in the same transactional store as
the data it identifies — not in a sidecar file that can be lost, copied, or
edited independently of what it describes.

**Comparison uses only the immutable fields:** project key, database name,
Compose project name, and instance UUID.

Explicitly *not* compared: the source commit, the manifest checksum, and the
template version. Those change legitimately on every redeploy. Including them
would make a valid volume start looking foreign after an ordinary upgrade, and
the first time an operator hit that they would learn to override the check —
which is the failure mode of every safety mechanism that cries wolf.

**A mismatch stops with exit `11`** (ADR 0031). Bootstrap never rewrites the row
to adopt a volume, under any flag. There is no `--force`, no `--adopt`, and no
`--i-know-what-i-am-doing`.

**The crash cases, which are what make this real rather than decorative:**

- a crash between sentinel commit and state publication **recovers** the UUID
  from the committed row. It never generates a new one against a non-empty
  volume;
- a candidate is discarded only when sentinel creation demonstrably never
  committed **and** an explicit check proves the volume is still uninitialised.
  "The state file is absent" is not that proof.

**Nothing removes a volume.** Not `deploy.sh`, not `bin/project-runtime.sh`, not
`bin/postgres-bootstrap.sh`, not `bin/migrate.sh`, not `bin/session-03-check.sh`,
under any flag. `bin/compose.sh` already refuses `-v` in edge scope; Session 3
extends that refusal to project scope, because `down -v` on a project stack is
the one command that destroys a database while looking like a stop.

Volume removal exists in exactly one place: an explicit disposable-project
command that refuses any project key other than the declared disposable one,
requires the key back as confirmation, and refuses when the target's identity
sentinel does not say disposable (D51).

## Consequences

Recovering from a genuine mismatch is deliberately manual: select the correct
volume, or write a reviewed migration plan. There is no automated remedy,
because every automated remedy for "this data might not be yours" ends in
adopting it.

The identity check needs the cluster running to read the sentinel, so it is a
host claim, not an offline one. What *is* provable offline is that no script
contains a volume-removing invocation.

Enforced by:

- `DBX-PG-003` — an existing data volume is bound to one project identity and a
  mismatch is refused (Run 5 offline, Run 8 live)
- `DEP-ISO-003` — two projects have isolated clusters, volumes, roles,
  credentials and identity sentinels (Run 8)
- `tests/contract/test_compose_wrapper.py` — `-v` is refused in project scope
  (Run 3)

## Alternatives considered

**Trust the volume name.** It is derived deterministically and it is already
unique per project. It is also the thing that is identical in every one of the
dangerous cases above, which is why ADR 0011 exists.

**A sentinel file inside the volume rather than a row in the database.** Easier
to read — no cluster needed, so the check could run offline. It can also be
copied by a `docker cp`, survive a `pg_upgrade` that discarded the data, or be
written by something that never wrote a byte of the database. The row is bound
to the data by the same transaction that stores it.

**Compare every field, including source commit and manifest checksum.** Strictly
more detection. It fires on every legitimate redeploy, so the check becomes
noise and the override becomes routine.

**Adopt on mismatch, with a loud warning.** Convergence always succeeds, which
is a real operational virtue. It also means the one situation the mechanism
exists to prevent — writing to data that belongs to another project — ends with
a warning in a log nobody reads and the write completing.

**Refuse only when the volume is non-empty.** Sounds safer and is narrower. An
empty-looking volume is exactly what a half-failed initialization leaves behind,
and that is when a wrong adoption is most likely and least visible.
