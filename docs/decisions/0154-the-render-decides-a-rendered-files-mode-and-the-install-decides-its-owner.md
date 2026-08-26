# 0154 — The render decides a rendered file's mode; the install decides its owner

- **Status:** accepted
- **Date:** 2026-08-26
- **Session:** 10, Run 11
- **Supersedes:** nothing. **Amends** the contract asserted by
  `tests/contract/test_rendered_migrations.py`, which three tests encoded as
  *"every rendered file is `0600` except two published snapshots"*.
- **Related:** ADR 0069 (the documentation container runs as 65532), ADR 0144
  (pgBackRest is installed into a derived Postgres image), ADR 0147 (the egress
  network), D226, **D588**, **D589**.

## Context

Three contract tests in `test_rendered_migrations.py` asserted a rendered
project directory's permission policy. They were written when the policy had
exactly two shapes — `0600` for everything, `0444` for the two reviewed OpenAPI
snapshots — and they encoded it as an **exemption list**: skip the names on the
list, assert `0600` on the rest, and separately assert that the list is closed.

Session 10 added a third shape. `pgbackrest.conf` is rendered for a container
running as **999**, and at `0600` root-owned it reached the archiver unreadable.
pgBackRest refuses such a file with `[041]: unable to open file … for read: [13]
Permission denied`, from two places at once — the deploy's step 6c and every
`archive_command` the postmaster runs afterwards (**D588**). The repair set
`PGBACKREST_CONF_MODE = 0o444`, and was incomplete, because `install_rendered`
re-imposed `0600` on everything it copied except the migration set (**D589**).
It was a *second* authority over a decision `rendering.py` had already taken
three times, and it won.

So two things had to change, and only one of them was the product.

## Decision

**One authority for a rendered file's mode: the render.** `install_rendered`
copies with `shutil.copytree`, whose `copy2` preserves modes, and then changes
**ownership only**. It performs no `chmod`. `rendering.py` names every mode it
uses — `FILE_MODE`, `MIGRATION_FILE_MODE`, `SNAPSHOT_MODE`,
`PGBACKREST_CONF_MODE` — and each carries the reason for its value at the
constant.

**And the three tests are replaced by stricter ones**, which is what this ADR
authorises. They are not relaxed to accommodate a third mode; the shape of the
assertion changes so that a third mode is *stated* rather than *exempted*:

1. **`RENDERED_EXEMPTIONS` (a set of names to skip) becomes `RENDERED_FILE_MODES`
   (a mapping of name → exact mode).** The old test asserted **nothing at all**
   about an exempted file — `openapi.json` could have been `0666` and stayed
   green. The replacement asserts an exact mode for every file including the
   widened ones, and fails on any file the mapping does not name. Strictly
   stronger in both directions.

2. **World-readability keeps its closed-list check and gains a content check.**
   The old test said *"only these two names may be world-readable"*. The
   replacement says that **and** that no world-readable rendered file contains
   credential material — asserted against `secrets_contract`'s option names
   rather than a hand-written list. A correctly-listed file that started
   carrying a secret used to pass; now it does not.

3. **A source-text scan becomes an AST assertion about what the code produces.**
   The old test asserted that the string `_is_migration_artifact` appeared in
   `bin/deploy-project.py` — D464's shape exactly, a string standing in for a
   construct, and it went red because the *correct* repair deleted the function.
   The replacement parses the module, finds `install_rendered`, and asserts it
   contains **no `chmod` call of any kind**. That is the property D589 actually
   established, and unlike the scan it cannot be satisfied by a mention or
   defeated by a rename.

## Consequences

- `pgbackrest.conf` is world-readable inside a directory that is `0700`
  root-owned on the host. Widening the file does not widen who can traverse to
  it — the argument `MIGRATION_FILE_MODE` already makes for the SQL, now made
  once for every artefact instead of re-argued per file.
- **The file carries no credential by construction.** `build_pgbackrest_conf`
  omits `repo1-s3-key`, `repo1-s3-key-secret` and `repo1-cipher-pass`; those
  arrive as per-consumer secret files under `/etc/pgbackrest/conf.d`, which is
  the `pgbackrest` format in `secrets_contract`. Two tests assert this, and
  after this ADR the world-readability test asserts it a third time from the
  other end — from the directory rather than from the renderer.
- **A future rendered artefact needs a decision, not an exemption.** Adding a
  file now means adding a row to `RENDERED_FILE_MODES` with its mode, and if
  that mode is world-readable the content check applies to it automatically.
- The residual is unchanged and stated in ADR 0147: the database container can
  reach the internet and holds the repository credential.

## What this does not decide

Whether `0444` or `0640 root:999` is the better shape. `0444` was chosen because
the enclosing directory already bounds the audience and because a group-owned
mode would make the *uid* a second thing the render has to know and keep in step
with the image. If a future session gives the rendered directory a wider
audience, that argument expires and this is the ADR to re-read.
