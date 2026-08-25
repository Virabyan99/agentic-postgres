# 0151 — The restore drill is disposable by construction, not by care

Status: accepted
Date: 2026-08-25
Session: 10, Run 8

Affects: D523, D558–D566, ADR 0002, ADR 0017, ADR 0144, ADR 0145, ADR 0147,
ADR 0149, `REC-SAFE-001`, `REC-PITR-001`,
`src/agentic_postgres/naming.py`, `src/agentic_postgres/restore_drill.py`,
`bin/restore-test.sh`, `bin/restore-test.py`,
`tests/contract/test_cli_contract.py`

## Context

D523 is the row this decision answers, and it is unusual in this repository for
saying up front that the obvious proof is defective:

> **An offline scan asserting the command's source never names the live volume is
> D277's shape** — an AST or text scan asking whether a name is *mentioned* is
> satisfied by dead code, and `test_no_operator_command_puts_a_service_directory_-
> on_the_path` (D464) is the standing example in this repository of a text scan
> producing a false positive.

Question 1 of the five: *what would have to break for this to go red?* A source
scan goes red only when somebody types a literal. Nobody types a literal. The
failure anybody actually fears is a **derivation** that produces the live name —
a truncation that collapses two identifiers onto one, a mount plan that copies
the wrong entry forward, a teardown that widens its search when it cannot find
its target. A scan sees none of those.

So the property has to be enforced where the argument vector is built, and proved
by driving the command until it produces one.

Rig 8 measured the third-party half against the derived Postgres image, the
pinned base digest and pgBackRest 2.59.1, with a posix repository standing in for
R2 exactly as rigs 5–7 used one. What a posix repository cannot measure is an
endpoint, a token scope or a 403; what it measures exactly is pgBackRest's own
restore behaviour, which is all this decision depends on.

## Decision

### 1. The drill's resources are derived, and their derivation cannot reach the live volume

`naming.restore_drill_names(key, drill_id)` derives the two names the drill owns:

```
volume            apg-<key>-restore-<drill_id>              context "compose_volume_restore_drill"
container         apg-<key>-restore-<drill_id>-pg           context "compose_container_restore_drill"
restore container apg-<key>-restore-<drill_id>-pgbackrest   context "compose_container_restore_drill_pgbackrest"
```

All three go through `compose_name`, the same function `postgres_volume` and
`postgres_container` go through, and each carries a context of its own.

**The first draft of this decision claimed the contexts were what kept these
apart from `apg-<key>-postgres`. That was wrong, and the mutation battery caught
it.** Arm Q7 changed the volume's context to `compose_volume_postgres` — the live
volume's own — and **nothing went red**. It could not: `truncate` fingerprints
`(context, value)`, and these values already differ from `apg-<key>-postgres` and
from each other, so the fingerprints differ whatever the contexts are. What
separates these names is the **stem**, and the contexts are convention with a
latent purpose: two derivations that ever shared a stem would still not collapse.

Recorded rather than quietly corrected, because the claim was the kind this
repository's §6 is about — an argument that sounded like `backup_bucket_name`'s
(ADR 0145) and was not, since *that* pair genuinely can share a stem and this one
cannot. The survivor is the evidence, and the battery is where a plausible wrong
sentence became a measured one.

**`-pg` and `-pgbackrest` are load-bearing, and the survivor is why they exist.**
Without them the volume and the instance container are the **same string** for
any key short enough to escape truncation and *different* strings for any key
long enough to hit it — an identity that is sometimes equal and sometimes not,
which is how a test comes to pass for a reason it does not state (D374).

`drill_id` is generated per drill and is not a project identity. It is in the
name so that a leftover from a crashed drill is a **different** resource from the
next drill's, rather than something the next drill silently adopts (see 4).

### 2. The drill inherits the archiver's configuration surface from the container that runs the archiver

The restore needs the repository credential, the cipher pass and the rendered
`pgbackrest.conf`. All three reach the *archiver* through the database
container's own mounts and environment, from the active secret generation — and
the active generation changes on every deploy, so **any path into it is derived,
never typed** (CLAUDE.md §7).

The drill therefore does not compute that path. It reads the running database
container with `docker inspect` and carries forward:

- every mount whose destination is one of the container paths the secrets
  contract and `runtime_override` name — the three backup secrets at
  `/run/secrets/<target_file>` and `PGBACKREST_CONF_CONTAINER_PATH` — remounted
  **read-only**;
- every environment variable in the `PGBACKREST_` namespace, which is pgBackRest's
  own and the only route arm 0 found for a credential that lives in a file (see
  D558).

Nothing else is carried: not the data volume, not the internal network, not
`POSTGRES_PASSWORD_FILE`. It is an allowlist of destinations, not a denylist of
the one that is dangerous — D300's rule, and the reason is that a denylist is
correct only for the entries somebody thought of.

The consequence worth stating: **when the archiver's credential path is built
(D558), the drill needs no change.** One fix, one place, two readers.

### 3. `--delta` is never passed, because pgBackRest's own refusal is the outer guard

Measured (rig 8, arm C-control):

| restore target directory | flags | exit |
|---|---|---|
| empty volume | none | **0** |
| the same volume, already restored into | none | **40** |

**pgBackRest refuses to restore over a populated directory.** `--delta` is the
flag that disarms that refusal, and it is the one flag that would turn "the
drill could not have overwritten anything" into "the drill overwrote whatever
was there". It is never on the argument vector, and an AST test refuses it — the
same shape as the AST test that refuses the WAL counters to
`archiving_is_failing` (ADR 0150), and for the same reason: passing it reads as
more robust than not passing it.

This is the guard that would still hold if every derivation in this document were
wrong at once. The in-process check in 5 is the guard that fires *first* and says
why.

### 4. A leftover is refused, never adopted

Measured (rig 8, arm J):

| operation | exit | note |
|---|---|---|
| `docker volume create X` where X exists | **0** | **adopts it**, and keeps X's original labels |
| `docker volume inspect X` where X is absent | 1 | |
| `docker run --mount type=volume,source=X` where X is absent | 0 | **creates X** |
| `docker volume rm X` where X is absent | 1 | |
| `docker volume rm -f X` where X is absent | **0** | the difference is hidden |
| `docker rm X` where X is absent | 1 | |
| `docker rm -f X` where X is absent | **0** | the difference is hidden |

Three rules follow, and none of them is a preference:

- **The pre-flight is `docker volume inspect`, not the exit code of
  `docker volume create`.** A `create` that returns 0 has told you nothing about
  whether the volume is yours.
- **The teardown uses `docker rm` and `docker volume rm` without `-f`**, so that
  "the target was already gone" is distinguishable from "the target was removed".
  §4.5 of the plan requires exactly this: *a teardown that cannot find its target
  exits non-zero rather than widening its search.*
- **A missing volume is not an error at mount time**, so a wrong target name
  produces an empty volume rather than a failure. That is survivable for the
  drill's target and is the reason the *source* side is an allowlist read off a
  running container rather than a name this command builds.

### 5. The disposability check runs in the product path, on the argument vector

`restore_drill.assert_disposable(plan, live_volume)` raises unless:

- the drill volume is not the live volume, and not any volume the live container
  mounts;
- no mount in the plan has the live volume as its source;
- the mount whose destination is `POSTGRES_VOLUME_TARGET` names the drill volume
  and nothing else;
- `--delta` is absent from the pgBackRest argument vector;
- the drill instance's command line carries `archive_mode=off` (see 6).

It runs on every invocation, before any `docker` process is started, and it is
what the offline rig's **control arm** drives: a deliberately wrong derivation —
the drill volume set to the live one — must be caught. An assertion that only
ever sees correct input is D509's shape, *a control that cannot fail for the
reason it is watching for*.

### 6. The drill instance never archives, and that is a second boundary

The restored instance promotes onto **timeline 2** (measured: `timeline_id` 2 on
the drill against 1 on the live cluster). A promoted instance with
`archive_mode=on` and the project's `archive_command` would push its own
divergent history into the project's stanza — the live volume untouched, and the
repository corrupted anyway.

So the drill container's command line carries `archive_mode=off` explicitly. It
is not left to the restored `postgresql.conf`: this project sets `archive_mode`
on the **command line** (ADR 0144), so the restored configuration file says
nothing about it, and relying on a default is relying on the absence of a setting
somebody may later add.

### 7. `system_identifier` is inherited by a restore and is not a discriminator

Measured, and it is the trap in this decision:

```
live  system_identifier = 7677917767700738081   timeline_id = 1
drill system_identifier = 7677917767700738081   timeline_id = 2
```

A restore is the same cluster at an earlier moment, so it carries the same system
identifier. **A host-side proof that read `system_identifier` to show "the live
cluster is untouched" would pass while reading the drill instance**, which is the
one mistake `REC-SAFE-001`'s host arm is most able to make. `timeline_id` is what
differs, and the volume's own identity — `instance_uuid`, which this project
generates once against an empty volume (`port_allocations`) — is what identifies
the volume.

## Consequences

- `bin/restore-test.sh` leaves `FUTURE_STUBS`, the fourth and final application
  of ADR 0017's lifecycle. `FUTURE_STUBS` becomes `()`,
  `test_the_remaining_stubs_are_the_ones_later_sessions_own` is replaced by a
  stricter assertion, and `test_database_commands.py`'s cross-module guard moves
  in the same commit (D524).
- The drill costs a second full copy of the cluster on disk for its duration.
  Host disk headroom is still unmeasured and is a pre-flight in the operator
  guide, not something to discover during a drill.
- **The drill cannot succeed on the host until D558 is closed.** The archiver has
  no credential path today, so neither does the drill — and it fails with
  pgBackRest's own `[037]: ... requires option: repo1-cipher-pass` rather than
  with a message this repository invented.
- `REC-SAFE-001`'s offline arm is buildable now and is Run 9's; its host arm needs
  a deployment. This run builds the capability and the guard the offline arm
  drives.

## Alternatives considered

**Mount the live volume read-only and restore beside it.** Simpler, and refused
by §9's stop conditions in as many words: *stop and ask rather than proceeding
when the restore path would be simpler if it mounted the live volume read-only.*
A read-only mount is one flag away from a read-write one, and the flag is on the
command that runs as root.

**Prove disposability with an AST or text scan of the source.** D523 rejects it
in advance and D464 is this repository's standing example of a text scan
producing a false positive. A scan asks whether a name is mentioned; the failure
is a derivation, and derivations mention nothing.

**Reuse one drill volume per project instead of one per drill.** Then the
teardown always knows its target and a leftover is never orphaned — but
`docker volume create` adopts an existing volume with exit 0 (arm J), so "reuse"
and "silently restore into whatever a crashed drill left" are the same code path.
Refused.

**Let the drill instance keep `archive_mode` at whatever the restored
configuration says.** Refused: the restored `postgresql.conf` says nothing about
it here, so this is relying on the absence of a setting.

**Derive the secret generation path in the restore command.** Refused by ADR
0002 and by the fact that the generation changes on every deploy. The running
container is the authority on which generation is active; a second derivation is
the copy that is right until the next `up`.
