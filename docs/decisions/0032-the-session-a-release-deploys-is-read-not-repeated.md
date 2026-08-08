# 0032 — The session a release deploys through is read, not repeated

- **Status:** Accepted
- **Date:** 2026-08-08
- **Session:** 3
- **Affects:** `deploy.sh`, `bin/deploy-project.py` (was `bin/deploy-session-2.py`),
  `bin/project-runtime.sh`, `libexec/agentic-postgres-project`,
  `src/agentic_postgres/deployed_output.py`, `schemas/outputs.schema.json`,
  `tests/contract/test_deploy_command.py`, `tests/contract/test_root_script_policy.py`

## Context

Run 7 of Session 3 opens with five commands against the host. The first is

```
sudo ./deploy.sh --host host.yaml --project project.alpha.yaml \
     --capabilities capabilities.yaml --through-session 3
```

and it exits `10`:

```
deploy: this release deploys through session 2; asked for 3.
```

The literal `2` in `deploy.sh` was correct for as long as 2 was the only value
anyone passed. Run 6 moved `CURRENT_SESSION` to `3` — the constant whose whole
job is to say which session this tree implements — and nothing connected the
two. The release that implements Session 3 refused to deploy Session 3.

It was not the only place. The session appeared as a literal in four:

| Where | As | What it selects |
|---|---|---|
| `deploy.sh` | `-le 2` | whether the deploy is allowed at all |
| `bin/deploy-session-2.py` | the filename, and a closing message | nothing, and the reader's belief |
| `bin/project-runtime.sh` | `--session 2`, `--profile session2` | which secrets exist, which services start |
| `libexec/agentic-postgres-project` | `--session 2` | the same two, at boot |

The last one is the one that matters most. The launcher runs with no operator to
ask. A Session 3 project restarted by systemd would have materialized Session 2's
secrets and started Session 2's profile — no cluster, no credential — and
`systemctl status` would have shown a unit that started cleanly.

## Decision

**The session is read from one place at each of the two moments it is needed.**

*Deciding what to deploy*: `deploy.sh` reads `CURRENT_SESSION` from the package
and refuses anything above it, naming the number it read. There is no second
declaration to drift.

*Restoring what was deployed*: the deployed document gains a required
`deployed_through_session`, and `libexec/agentic-postgres-project` reads it with
the same `jq` it already uses for `source_commit`. `bin/project-runtime.sh`
takes `--through-session N` as a **required** flag for `up` and `down` — not a
defaulted one, because a default is the literal this decision removes.

The entry point is renamed `bin/deploy-project.py` and takes `--through-session`.
Its old name described the one session it could do; ADRs 0020, 0021 and 0023
still refer to `bin/deploy-session-2.py` and are left alone, because an ADR
records what was decided when it was decided.

The Compose profile set is derived cumulatively — a session-3 deployment starts
`session2` and `session3` — by one function in `bin/project-runtime.sh`, so
"which profiles is session N" has a single answer.

## Consequences

A deployed document written by an earlier release has no
`deployed_through_session`, and the launcher exits `4` naming the field and the
remedy rather than guessing `2`. Both projects on the host are redeployed in
Runs 7 and 8, which is when they acquire it. Guessing would have been the same
defect with a friendlier face: the guess is right until the first project it is
wrong for, and that project is the one with a database.

`--through-session` is now required by `bin/project-runtime.sh`, so any caller
that forgot it fails loudly instead of starting a subset. There are exactly two
callers, and both are in this repository.

The schema's `deployed_through_session` has `minimum: 2`. Sessions before that
start no container, so a document claiming one would describe something that
never happened.

## Alternatives considered

**Clamp instead of refuse.** Rejected in Session 2 and still rejected: deploying
less than was asked for and reporting success is the failure discovered in
production.

**Keep the ceiling as a literal and update it each session.** This is what
existed. It is one edit per session in a file nobody edits per session, which is
why it was missed.

**Record the session in the project's state directory rather than in the
deployed document.** A separate file would need its own writer, its own
permissions and its own place in
`test_every_state_file_a_launcher_requires_has_a_writer`. The deployed document
is already the record of what was deployed, already read by this launcher, and
already schema-validated.

**Derive the session at boot from what is installed** — for example, by looking
for a postgres container. That reads the effect to determine the intent, so a
project whose cluster failed to start would be "restored" as a session-2
project, and the restore would look successful.
