# 0071 — A read-only diagnostic surface for an unprivileged agent

Status: accepted
Date: 2026-08-13
Session: 5, Run 10
Amends: the operator rule in `CLAUDE.md` §5

## Context

Every privileged action on this host is run by a human at a terminal, because
`sudo` needs a TTY and because a deploy can destroy a volume. That rule has held
since Session 2 and it is not in question here.

What is in question is everything else. Diagnosing D207 and D208 took five
round-trips through a human relay, and **every command in them was read-only** —
`docker ps`, `docker inspect`, `docker logs`, `curl`, an attempt to read
Traefik's API. None of them changed anything. Two of the five were wasted on
instruments that turned out not to work: an empty response from a Traefik API
that is not enabled, nearly read as "there is no router".

A relay that slows down asking questions does not make the answers better. What
caught the defects in this session was *running things*, not a human retyping
them.

**The constraint that shapes everything below:** on this host, docker access is
root access. The daemon socket can mount the host filesystem, so "let the agent
run docker" and "give the agent root" are the same sentence, and the docker
group has no middle setting.

## Decision

**A separate `apg-agent` account, with a `NOPASSWD` sudoers rule naming exactly
one root-owned script, whose arguments are an allowlist.**

`bin/apg-diag.sh` answers eight questions and nothing else: `containers`,
`labels`, `logs`, `routes`, `listeners`, `edge-log`, `catalog`, `generation`.

The constraints live in the script rather than in `/etc/sudoers.d`, and that is
deliberate. Sudoers can constrain arguments, but its syntax cannot express "a
project that exists on this host" or "one of these four queries" — a rule that
tried would be a glob or a list nobody keeps current. So the rule grants one
absolute path and the script is where the boundary is written, reviewed and
tested.

Four properties make that mean something, and they are `bin/db.sh`'s, applied to
a different daemon:

1. **The verbs are a fixed set of names, not a passthrough.** A wrapper that
   forwarded its arguments to `docker` would be the same door with a lock
   painted on it.
2. **A project is validated against what is deployed**, not against a pattern. A
   regex accepts `../../etc` for exactly as long as somebody keeps the regex
   right.
3. **The SQL is an allowlist of named queries.** No path takes SQL from an
   argument or from stdin.
4. **Nothing mutates.** No restart, stop, rm, run, `systemctl`, or `docker exec`
   with a caller's command. A diagnostic that can change what it describes is
   not a diagnostic.

And two about what cannot leave through it: `docker inspect` is restricted to
`.Config.Labels`, because unfiltered it prints the environment, the mounts and
the command line — three of the four places a secret must not be; and `logs`
passes through a redaction filter, which is belt to the braces of those services
not logging credentials in the first place.

**The installed copy lives at `/usr/local/bin/apg-diag`, root-owned.** Not a path
inside a release: `installed_release` refuses symlinks, so there is no `current`
to point at, and a rule naming a release sha would break on the next deploy. A
`NOPASSWD` rule pointing at a file its beneficiary can edit is a root shell with
extra steps, and the agent has a checkout.

The script imports nothing from the repository. That began as a consequence of
being a copy and is now a property worth keeping: it answers when the checkout is
broken, mid-deploy, or at a release about to be rolled back — which is when the
questions get asked.

## What stays with a human

Deploys, the bootstrap plane, migrations, rotations, `systemctl`, and anything
that reads a credential. Not because a human catches more mistakes — this
session is fairly strong evidence that what catches them is running the thing —
but for two reasons that survive that:

- **Blast radius.** An agent that can deploy can destroy a volume or rotate a
  credential nobody can recover. Today the worst outcome is a bad commit.
- **Secret exposure.** No credential value has passed through this agent's hands
  in the whole of Session 5. An account that can deploy can read every
  materialized secret, and that property is worth more than the round-trips it
  costs.

Two smaller ones: the ACME cap is five failed validations per hour per hostname,
which an agent in a retry loop burns in a minute; and a shared account makes
"who did this" unanswerable afterwards, which is why this is a *separate*
account with its own key and `log_output` enabled.

## Alternatives

**Add the agent to the `docker` group.** Rejected: that is root, with no
gradation, and it would silently include every mutating verb.

**One account for the agent and the operator.** Rejected: attribution. The sudo
log would not distinguish them, and the first question after an incident is who
ran what.

**Constrain arguments in the sudoers rule.** Rejected as weaker than it looks —
see above. It also puts the boundary in a file with no tests, where this one has
forty-two.

**Nothing; keep relaying.** Rejected, but it was the right default until now.
What changed is that the questions became frequent and uniformly read-only.

**Capture diagnostics automatically on failure instead.** Not rejected —
complementary, and worth doing. A failing gate that wrote its own context bundle
would remove a different set of round-trips, and it grants nothing at all.

## Consequences

- The agent can answer "what is this deployment doing" without a human present,
  and can be wrong more cheaply.
- **A new verb is new privilege.** `tests/contract/test_diagnostic_surface.py`
  asserts the verb list twice — in the script and in the test — so adding one
  without review fails.
- `CLAUDE.md` §5's rule is amended rather than broken: privileged *mutation* is
  still a human at a terminal. The line is updated to say so, because a rule the
  host no longer follows is worse than no rule.
- The copy at `/usr/local/bin/apg-diag` drifts from the repository until somebody
  re-installs it. That is a real cost, accepted because the alternative couples
  the diagnostic surface to a release path that changes.
- Writing the tests for this produced **five instances of one mistake in one
  file**: a scan whose token also appears in the thing being scanned — `"ls "`
  matching `labels logs`, `"cat "` matching a heredoc, `"_root"` matching
  `require_root`, `"pgpass"` matching the redaction rule that removes pgpass, and
  a sudoers split landing inside the comment explaining what a `NOPASSWD` rule
  is. Recorded because the repair is always the same: assert the property, not a
  substring that correlates with it.
