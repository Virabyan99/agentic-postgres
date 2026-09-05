# 0189 — A replacement host is built from a kit that names every secret and holds none, and the bootstrap adopts by recorded id

- **Status:** accepted
- **Date:** 2026-09-05
- **Session:** 18, Run 1 (`REC-KIT-001`, `REC-KIT-002`, `REC-NODE-001`, `REC-NODE-002`, D715, D986, D987)
- **Related:** **ADR 0010** (secrets are files, never arguments), **ADR 0011**
  (the bootstrap records what it created, by id), **ADR 0030** (a volume
  carries an identity and a mismatch is never adopted), **ADR 0110** (nothing in
  this repository creates a bucket), **ADR 0151** (the drill never mounts the
  active volume), **ADR 0188** (the mirror), the provider-bootstrap runbook's
  stop condition (*never adopt by name*).

## Context

The stage plan's Session 18 asks that *"a project restores onto a clean
replacement host using only the independent backup account and documented
artifacts"*. Checked against the tree (D986), no document defines those
artifacts, and the bootstrap cannot start on a host that has no state:
`bootstrap-providers.sh --apply` creates an Infisical project and identity BY
NAME, the original project's Infisical project already exists under that name,
and adopting by name is the runbook's stop condition for a good reason -- two
similarly named identities are how the wrong one gets a credential. The
runtime credential and `bootstrap-state.json` are root-only files on the host
that is gone, and `restore-test.sh` restores only into a disposable volume by
design.

So the question is what an operator must be holding, off the host, on the day
the host is gone -- and what may be in it.

## Decision

**`bin/dr-kit.sh export` writes the kit; `verify` checks one; the kit holds
identifiers and never a value.** It contains, per project: the host manifest,
the project manifest, the capability manifest, `bootstrap-state.json` (provider
ids, the convergence key, the credential paths), and `secrets.txt` naming every
secret's provider key and provider path with no value. A proof plants the
sentinel and asserts the kit does not carry it. Where a value lives is what the
kit says: the cipher pass, the runtime passwords and the mirror credential in
the project's Infisical project; the control-plane credential with the
operator; the mirror's bucket at the second provider.

**`bootstrap-providers.sh --adopt --state FILE --operator-credential-file FILE`
binds a host to the Infisical project the state records BY ID.** It mints a
fresh runtime identity against that project, grants it read, writes the two
credential files and a new state that carries the recorded project id; it
refuses when the recorded id does not exist and it never searches by name.
`--apply` is unchanged and still refuses to adopt.

**`bin/restore.sh --outputs FILE --from CONFIG --latest|--target-time T`
restores a stanza into the project's own volume, and only when that volume
holds no cluster.** It runs the same image and mounts the drill runs, passes
never `--delta` (pgBackRest's own refusal, `[040]`, is then the last guard, D997),
refuses when the stanza in the configuration does not match the document's,
and records `evidence/restore-<key>-<id>.json` in the drill's shape. On the
production host it is never run; on a replacement host the project's volume
is empty by construction.

**The node-loss runbook is the order**: provision the replacement by the
documented path; `dr-kit.sh verify`; `--adopt` per project; the control-plane
credential shredded; materialize; deploy the project with its manifest's
`backup` block pointing at the mirror bucket as the primary (a mirror is a
repository); `restore.sh --latest`; verify by the original `instance_uuid` and
the row counts of the last copied set; then, as the last step and the one the
trip rehearses as a plan and never performs, the DNS cutover.

## What this refuses

- A kit that holds a secret value, a token, or a credential file. An operator
  who wants a value in the kit is asking for a second secret store with no
  rotation, no audit and no owner.
- Adoption by name, at any provider.
- A restore into a volume that holds a cluster, on any host.

## Consequences

- Run 3 builds the two verbs, `--adopt`, and the runbook derived by diff from
  the Session 11 and 17 guides.
- The trip's replacement host is built from a kit exported from production
  with the primary provider's credential never present on it.
- `fresh_host` (`DEP-001`) is still closed by a NEW project deployed on the
  replacement by the documented path, before the restore (D987); the kit and
  the restore close `replacement_host_restore`.
