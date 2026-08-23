# 0147 — The database reaches its repository over an egress network of its own

Status: accepted
Date: 2026-08-23
Session: 10, Run 4

Affects: REC-PITR-001, REC-WAL-001, THR-BACKUP-COMPROMISE, D516, D539,
`compose.yaml`, `src/agentic_postgres/naming.py`,
`src/agentic_postgres/rendering.py`

## Context

`archive_command` is run by the postmaster, inside the Postgres container
(ADR 0144). The Postgres container was on `internal` and only `internal`, and
that network is declared `internal: true` — "No route off the host."

Measured in Run 1 (rig1 arm E), with the pair as its own control: a container on
a plain user-defined bridge resolved `r2.cloudflarestorage.com` to `172.64.190.1`
and connected on 443; the same image on an `--internal` network failed **both**
DNS and TCP. So the boundary is real, and `archive-push` could not reach the
repository from where the postmaster runs it. Something had to change.

Three ways to change it:

- put `postgres` on the existing `edge` network;
- give it a network of its own;
- keep it off egress entirely and have a sidecar relay the archive (ADR 0144's
  rejected TLS-server topology, which still needs the client in this container).

`compose.yaml` says "only Traefik will ever straddle both networks", and that
comment has been two-thirds true since Session 7, when `storage` joined
`internal` and `edge`. What has never happened is the *database* being on the
network Traefik's public side lives on.

## Decision

**A third network per project, `apg-<key>-backup`: egress, no Traefik, no
published port, and exactly one member.**

- `naming.backup_network_name(key)` derives it, like every other network name.
- `postgres.networks` is `[internal, backup]`. It is not on `edge`, and a test
  asserts the absence rather than the presence alone.
- The network is **not** `internal: true`, and a test asserts that too — a
  later edit "hardening" it would silently stop every backup, and the failure
  would appear at the next archive-push rather than at the edit.
- It is declared and rendered for every project, enabled or not: `compose.yaml`
  interpolates the name unconditionally and Compose refuses an empty value as
  firmly as an unset one (D178, ADR 0062).

## Consequences

**The database container can now reach the internet, and it could not before.**
That is the cost, it is not mitigated by anything here, and it is written down
rather than implied. A compromised postgres container reaches R2 with the
repository credential and the cipher pass, which are both mounted into it
(ADR 0145) — so an attacker who owns that container owns the backups as well as
the live data.

What the narrower network buys over `edge` is real but modest: the database is
not on the segment Traefik's public listener lives on, so a Traefik-side
compromise does not find a Postgres port one hop away. It buys nothing against
an attacker already inside the database container.

**`test_the_backup_network_carries_the_database_and_nothing_else` is the control
on that cost.** The egress network exists for one command in one container, and
nothing else counts its members. A second service added later would widen what
can reach the internet from inside a project, invisibly.

**`test_postgres_joins_only_the_internal_network` was replaced, not relaxed.**
The old assertion was `networks == ["internal"]`, which would have been
satisfied by any single network including `edge`. The replacement pins both
members and asserts `edge` is not among them, which is strictly more than the
original said (ADR 0096).

**A fourth network would need a reason, and there is no mechanism forcing one.**
Nothing prevents a future session adding `postgres` to `edge` beside these two;
what exists is a test that would go red and a comment saying why. That is the
same standing this project's other network rules have.

## Alternatives considered

**Put `postgres` on `edge`.** Fewest new objects, and `storage` is the
precedent. Rejected: it places the database on the network carrying Traefik's
public side, which is the one boundary this repository has kept even while
loosening the comment that describes it. The gain was one fewer network object
per project.

**A pgBackRest TLS-server sidecar, with `postgres` off egress entirely.** The
only option that keeps the database unable to reach the internet. Rejected in
ADR 0144 and re-rejected here: it still requires the pgBackRest client in this
container, so it adds a mutual-TLS cert pair and an unmeasured topology *on top
of* this decision rather than instead of it. And an attacker inside the postgres
container could drive the sidecar anyway, so the residual risk above is reduced
less than it appears.

**A host-level egress proxy.** Not considered seriously for Session 10: it moves
the credential out of the container, which is the real prize, but it is a new
service with its own authentication, its own failure modes and its own
operator surface. Recorded because it is the shape that would actually retire
this ADR's cost.
