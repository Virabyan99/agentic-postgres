# 0037 — An installed launcher resolves a release and nothing else

Status: accepted
Date: 2026-08-08
Session: 3, Run 8

## Context

`agentic-postgres-project@<key>.service` executes
`/usr/local/libexec/agentic-postgres/project`. That file is installed by
`bin/provision-host.sh`, whose own comment says why it is installed from the
checkout rather than from a release:

> these are the *indirection*, not the code they resolve to, and they change
> only when the repository changes.

The repository changed. In Run 7, D59 moved the deployment session out of four
hard-coded literals and into the deployed document, and the launcher was one of
the four — the serious one, because it runs at boot with no operator to ask.
That fix was written, reviewed, tested offline, and shipped inside two releases
that were installed on the host.

It never ran. Nothing but provisioning installs a launcher, and the host was
provisioned in Session 2. The first `systemctl restart` of a Session 3 project,
in Run 8, executed a Session 2 launcher:

- `materialize` ran with `--session 2`, wrote a secret generation holding
  Session 2's secret set — no `postgres_init_superuser_password`, no
  `migration_user_password` — and **repointed the project at it**;
- `up` then invoked `project-runtime.sh` with no `--through-session` and exited
  `2`;
- `ExecStopPost` ran `down`, which failed the same way and stopped nothing.

Both projects landed in `failed` with their containers still running, which is
why nothing was visibly wrong. A reboot would have brought neither back.

Every existing DEP-REL-001 proof passed throughout. They all characterise the
*release*: named for a full commit, root-owned, not a checkout, and the units
execute only a libexec path. Not one compared the file systemd actually runs
against the file the repository ships, because until now the two were expected
to differ and the difference had no name.

## Decision

**A launcher installed in `/usr/local/libexec/agentic-postgres/` may resolve a
release. It may not hold an answer that belongs to one.**

Concretely:

1. `libexec/agentic-postgres-project` becomes a trampoline. It validates the
   systemd instance name, reads the project's deployed document, validates and
   resolves `source_commit` to an installed release, checks that release is
   root-owned and unsymlinked, and `exec`s
   `<release>/libexec/project-launcher`. That fixed path is the interface
   between provisioning and every release.

2. `libexec/project-launcher` is new and ships **inside** the release. It reads
   `deployed_through_session`, resolves the copied manifests, and dispatches
   each action to this release's scripts. It is deliberately not named
   `agentic-postgres-*`, because that glob is what gets installed, and a copy of
   it outside a release would be a second answer to the question D59 and D72
   were both about.

3. `installed_release.reconcile_launchers` installs the trampolines from the
   release, and the deploy calls it immediately after installing the release.
   Written beside and renamed rather than truncated in place: systemd may be
   executing the file, and a partially written launcher is one a reboot runs.

4. A launcher's release-independence is asserted structurally, over source with
   comments stripped: no `--session`, no `--through-session`, no `--profile`, no
   `secrets.required.yaml`.

5. A host test compares the installed launchers byte-for-byte against the ones
   the repository ships.

## Consequences

One copy of each trampoline serves every project on the host, including projects
deployed through other releases, so a deploy of one project overwrites a file
another project's boot depends on. That is safe **only** because of point 4, and
point 4 is a test rather than an intention.

A release that predates this ADR carries no `libexec/project-launcher`. The
trampoline says so and exits `4` naming the project to redeploy, rather than
falling back to logic of its own — a fallback here is how a Session 3 project
gets started as a Session 2 one, which is the thing that happened.

Point 5 fails if the checkout is moved to a commit nobody deployed. That is a
false positive by one reading and the correct signal by another: the host is
executing a launcher that is not the one under review.

## Alternatives considered

**Install launchers from the release and leave their contents alone.** Cheaper,
and it fixes the immediate defect. Rejected because it makes the shared file
release-dependent while still shared: a launcher from release X would then have
to launch a project deployed through release Y correctly, forever. Today's
launcher would fail loudly in that case, which is better than silence and worse
than not having the case.

**Make the units name the release directly.** Then no indirection exists to
drift. Rejected: the unit is static and installed once, so it would have to be
rewritten on every deploy, which moves the same problem into a file systemd
parses at boot.

**A gate check that the installed launcher matches, with no automatic install.**
That is point 5 alone. It converts a silent defect into a loud one and leaves
the operator to fix it by hand every release. Kept, as the proof — not as the
mechanism.

## Proofs

- `tests/contract/test_host_infrastructure.py::test_the_project_trampoline_delegates_to_the_release`
- `tests/contract/test_host_infrastructure.py::test_an_installed_launcher_holds_no_answer_a_release_owns`
- `tests/contract/test_host_infrastructure.py::test_the_release_side_launcher_is_not_installed_anywhere`
- `tests/contract/test_host_infrastructure.py::test_the_release_side_launcher_reads_the_session_from_the_document`
- `tests/contract/test_installed_release.py::test_the_deploy_reconciles_the_launchers_it_ships`
- `tests/security/test_session2_installed_release.py::test_the_installed_launchers_are_the_ones_this_release_ships`
- `tests/deployment/test_session3_convergence.py::test_restarting_the_project_unit_brings_back_the_recorded_session`
