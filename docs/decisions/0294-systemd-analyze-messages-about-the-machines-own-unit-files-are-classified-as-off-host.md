# 0294 — `systemd-analyze` messages about the machine's own unit files are classified as off-host

- **Status:** Accepted
- **Date:** 2026-10-29
- **Session:** 46, Run 11 (`docs/plans/session-46-implementation-plan.md`, D2942)
- **Affects:** `tests/contract/test_host_infrastructure.py`
  (`_EXPECTED_OFF_HOST`'s companion `_about_a_unit_the_repository_does_not_ship`,
  `_unexplained`, the new `test_the_classifier_explains_only_what_is_not_about_our_units`,
  and `test_systemd_analyze_accepts_the_units`, which now calls `_unexplained`).
  No product file changes.
- **Related:** CLAUDE.md §6 (*a contract test changes only with an ADR; widening an
  allowlist to a measured set is not weakening*), D2942.

## Context

`test_systemd_analyze_accepts_the_units` runs `systemd-analyze verify` over the
four unit files under `systemd/` and fails on any message `_EXPECTED_OFF_HOST`
does not classify. That tuple holds two facts about a machine that is not the
deployment host: Docker is not a unit there, and the launchers are not installed
at `/usr/local/libexec/agentic-postgres/`.

`verify` also loads the machine's OWN units while it resolves our dependencies,
and reports what it finds in them. After `55467b5`'s green run (2026-10-26),
GitHub's `ubuntu-latest` runner image began shipping units that set an option the
image's systemd has removed. Every push since `a34c906` failed both CI jobs on
the same three lines (run 40846812354, 2026-10-29):

```
/usr/lib/systemd/system/xfs_scrub_all.service:26: Support for option CPUAccounting= has been removed and it is ignored
/usr/lib/systemd/system/system-xfs_scrub.slice:15: Support for option CPUAccounting= has been removed and it is ignored
/usr/lib/systemd/system/walinuxagent.service:21: Support for option CPUAccounting= has been removed and it is ignored
```

None of those files is ours. The release was unaffected: `publish-cli` verifies
the tagged commit's own `contract` run.

## Decision

1. **A message `verify` locates in one of the machine's unit directories**
   (`/usr/lib/systemd/system/`, `/lib/systemd/system/`, `/etc/systemd/system/` —
   the first measured, the other two the same directory's other names on a
   Debian-family host and the administrator's directory) **in a file whose name is
   not one of the repository's `UNITS`** is classified as off-host. Located means
   `verify`'s own `<absolute path>:<line>: ` prefix.
2. **A message about a unit the repository ships is never classified away** —
   at its checkout path, or installed on the machine under its own name. An
   unlocated message is never classified away either.
3. **The class is located by FILE, not by message text.** Matching the
   `CPUAccounting=` sentence would pass the next drift's sentence about the same
   foreign files and still fail it; matching any message would pass a real error
   in our units.
4. The classification is a named function, proved offline by
   `test_the_classifier_explains_only_what_is_not_about_our_units` on the three
   measured lines and on five lines it must keep: the same sentence in our unit at
   its checkout path, in two of our units installed under the machine's
   directories, in a foreign file outside them, and an unlocated line. Its
   mutation battery (Run 11) kills each half of the rule — our names unprotected,
   any directory taken for the machine's, the classifier unconsulted, an
   unlocated line explained — against a control no mutation reaches.

## Alternatives

- **Pin the runner image** (`runs-on: ubuntu-latest` → a versioned label). Moves
  the drift to the next label change rather than classifying it, and the
  versioned images are updated in place too.
- **Accept the exit code when every message is a warning.** `verify` does not
  mark severity in a parseable way, and accepting a class of exit codes accepts a
  unit that does not parse — the reason `_EXPECTED_OFF_HOST` is classified, not
  tolerated.
- **Run `verify` with `--root` on an empty tree.** Then our dependencies
  (`docker.service`, `network-online.target`) are unresolvable by construction
  and the test reads only those messages: a different test.

## Consequences

- main's CI reads the units again on a runner whose own units drift.
- A machine unit that shares a name with one of ours is still reported — a
  deliberate false alarm rather than a silent pass.
- The tuple and the function together are the whole allowlist; neither reads
  the message's text for the machine's files.
