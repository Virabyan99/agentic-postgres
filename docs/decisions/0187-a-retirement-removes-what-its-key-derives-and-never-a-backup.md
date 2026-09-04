# 0187 — A retirement removes what its key derives and its state records, on this host, and never a backup

- **Status:** accepted
- **Date:** 2026-09-04
- **Session:** 17, Run 4 (`FLEET-RETIRE-001`, `FLEET-RETIRE-002`, `FLEET-EXPIRE-001`, D691, D951, D956, D957)
- **Related:** **ADR 0002** (an identity is derived once), **ADR 0011** (the
  bootstrap records what it created, by id, and destroys nothing else), **ADR
  0030** (a volume carries an identity and a mismatch is never adopted), **ADR
  0042** (a port allocation is keyed by that identity), **ADR 0110** (nothing in
  this repository creates a bucket), **ADR 0145** (the backup repository has
  its own bucket and cipher pass), **ADR 0151** (the drill never mounts the
  active volume), **ADR 0186** (expiry is a fact an operator reads), **D691**
  (no shipped command removed a project), **D713** (a TTL that expires into
  destroying the cipher pass is a data-loss timer), **D957** (`--destroy` leaves
  every secret in place).

## Context

Since Session 12 (D691) the removal surface has been two commands:
`project-runtime.sh down`, which keeps the volume so that a `systemctl
restart` is never a data-loss command, and `bootstrap-providers.sh --destroy
--confirm KEY`, which revokes the runtime identity and — measured at this
session's planning (D957) — leaves every Infisical secret in place, the
cipher pass included. `compose.sh` refuses `--volumes` in project mode.
`DEP-REMOVE-001`'s proof has waited four sessions for a project to be
actually removed, and only two exist.

What a retirement has to reach was measured (D951): ten containers, three
networks, two volumes, one enabled systemd instance, two timers once D944 is
repaired, the state directory, the secrets and rendered directories, the edge's
two project files, and the port allocation — on the host. Off the host: the
runtime identity (the one thing `--destroy` reaches), two R2 buckets and two
tokens created by hand, a DNS record, a certificate in `acme.json`.

The question this ADR answers is the one the stage plan's D713 named: **what
may a destroy-the-data verb destroy?**

## Decision

**`bin/project-retire.sh` removes what the project's key derives through
`naming` and what its own state records, on this host, in one fixed order —
and never the backup repository, its bucket, the cipher pass, the Infisical
project's secrets, the DNS record or the certificate.**

### What is removed, and where each name comes from

Every name is derived from the key (`naming.compose_project_name`,
`postgres_volume_name`, `store_volume_name`, `backup_network_name`, the
systemd instance, the two timer instances, the three directories, the two
edge files) or read off the deployed document the deploy wrote under that
key (the two project networks, the instance uuid, the release). Nothing is
typed, and a document under one key that names another project is refused
before any name is derived. The scoping proof is the one `DEP-REMOVE-001`
already runs: the other project on the host serves and holds its rows after.

### The order is a contract (D956)

`retirement.STEP_ORDER`: the **record** first, before anything changes,
because a record captured afterwards lists things that no longer exist;
**down**; the **units** disabled; the **port allocation released** under the
volume's identity, *before* any volume is removed, because after the volume
is gone nothing can name the allocation (ADR 0042); the **edge files**; the
**provider destroy**, *before* the state directory is removed, because it
reads the installed manifest and the bootstrap state out of that directory;
the three **directories**; and, only with `--destroy-data`, the two
**volumes**. A step that fails stops the run, names itself, and the steps
after it do not run; the record already says what was intended.

### What is never removed, and the record says where it is

The backup repository stays in its bucket under its stanza, readable with the
cipher pass the Infisical project still holds — because `--destroy` never
exercised the licence `managed_resources` grants it (D957), and this verb
does not add that step. Deleting the bucket and the Infisical project are
console actions, and the retirement record names them in a sentence so the
operator's next step is written down rather than remembered. **Nothing here
reaches `pgbackrest`, a bucket, a token or DNS.** `FLEET-RETIRE-002` asserts
no command in the plan names the bucket or the stanza.

### The refusals come first, and there is no `--force`

The key is said back with `--confirm` (bootstrap-providers.sh's rule); a
permanent project needs `--permanent`; an ephemeral project that has not
reached its `expires_at` needs `--before-expiry`; an expired one needs
neither, and a flag that does not apply is refused rather than ignored (D374
at the terminal). The record path must not exist. `--plan` prints every name
and every command and mutates nothing.

### Volume removal now lives in two places

`test_neither_command_can_remove_a_volume` said volume removal existed in
exactly one place, the restore drill's own volume (ADR 0151). It exists in two
now, and a test enumerates both so a third arrives as a decision. Without
`--destroy-data` the volumes are kept by name: a redeploy of the same key
adopts them only if the identity matches (ADR 0030).

### Expiry is read, never acted on

No unit, timer, cron, deploy step or command in the release names the verb;
`FLEET-EXPIRE-001`'s offline half scans `systemd/`, `libexec/`, `bin/`,
`compose.yaml` and `deploy.sh` for it. The inventory reports an expired project
and the verb refuses an unexpired one. That is the whole automation.

## Consequences

- `project_removal` (`DEP-REMOVE-001`, Session 12) can close on the trip: the
  verb writes the record `APG_REMOVED_PROJECT_FILE` reads, captured before the
  removal, and the third project exists to be retired (D953).
- Two host paths are spelled once: `edge_state.EDGE_DYNAMIC_DIR` replaces the
  copy `deploy-project.py` carried; `secret_generation.SECRET_ROOT` and
  `deployed_output.RENDERED_ROOT` were already the one spelling.
- A retirement leaves the R2 buckets, the tokens, the DNS record and the
  certificate for the operator; a session that wants any of them removed by
  code starts from ADR 0110, which says nothing here creates a bucket.
- The provider destroy needs the operator's control-plane credential file
  when bootstrap state exists; the verb refuses up front rather than after
  `down`, so a retirement never stops halfway for want of a token.
