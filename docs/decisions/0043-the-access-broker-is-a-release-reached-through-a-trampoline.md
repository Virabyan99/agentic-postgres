# 0043 — The access broker is a release, reached through a trampoline

Status: accepted, with two amendments made on acceptance
Date: 2026-08-08
Accepted: 2026-08-09 (Session 4, Run 6)
Session: 4, Run 1
Affects: DX-DB-001, DX-DB-002

Accepted in Run 6, the run that wrote the broker. The amendments are at the
bottom, under **Amended on acceptance**. Both are things that writing it made
true and that proposing it had not: one narrows a claim that could not hold
where it was stated, and one renames a file whose name collided with the
trampoline's.

## Context

`bin/connect.sh` runs unprivileged, as a developer. The things it needs —
a project's deployed document, its allocated ports, and one password from the
active secret generation — are root-owned by design. Something privileged has to
stand between them, decide whether this caller may have this profile of this
project, and hand back the minimum.

The Session 4 runbook put that program at
`/usr/local/libexec/agentic-postgres/database-access`, exposed through a narrow
`sudo -n` rule.

That directory is the one ADR 0037 constrains. **An installed launcher may
resolve a release and nothing else**, because one copy of it serves every
project on the host, including projects deployed through releases it has never
seen. A broker that validates policy, reads per-project state and returns
secrets is precisely the release-owned logic that ADR forbids there.

The reason it forbids it is not theoretical. A Session 2 launcher ran
`--session 2` against a Session 3 project for three runs, wrote a secret
generation holding the wrong secret set, repointed the project at it, and left
both units `failed` with their containers still running. Every proof passed
throughout. Reintroducing that shape in the one program that hands out
credentials is the worst available place for it.

## Decision

**The broker follows the trampoline split.**

1. `libexec/agentic-postgres-database-access` is installed by the deploy
   alongside the other trampolines. It validates its arguments, reads the
   project's deployed document, resolves and validates `source_commit` to a
   root-owned installed release, and `exec`s
   `<release>/libexec/database-access`. It holds no policy.

2. `libexec/database-access-broker` (renamed on acceptance — see below) ships
   **inside** the release and holds every decision: which profiles exist, which
   callers may have them, which secret name each maps to, and what is returned.
   It is deliberately not named `agentic-postgres-*`, because that glob is what
   `provision-host.sh` installs.

3. The structural test that an installed launcher holds no answer a release owns
   covers the new trampoline automatically — it globs the directory rather than
   naming files.

4. The operation set is enumerated. No caller-supplied path, no arbitrary secret
   name, no pass-through of a profile string into a filesystem lookup. The
   policy file is root-owned, schema-validated, and published atomically.

5. The broker returns a credential on stdout to an authorized caller and
   **nothing at all** to an unauthorized one — no partial answer, no
   confirmation that the project exists, no distinction in exit code between
   "no such project" and "not yours". *Amended on acceptance: this is a property
   of the broker, past the trampoline, and the amendment below says why it
   cannot be one of the trampoline.*

## Consequences

One copy of the trampoline serves projects deployed through different releases,
so a deploy of one project overwrites a file another project's access path
depends on. That is safe only because of point 3, and point 3 is a test rather
than an intention — the same bargain ADR 0037 struck, and the same reason it is
acceptable.

A release predating this ADR carries no `libexec/database-access-broker`. The
trampoline says so and exits `4` naming the project to redeploy, rather than
falling back to logic of its own. (`4`, not the `3` first written here: a
release that is installed and incomplete is missing runtime state, and `3` is
for a prerequisite that was never installed at all. The project launcher already
uses `4` for the same condition.)

The `sudo -n` rule names the trampoline path, which never changes, so the
sudoers entry is written once at provisioning and not rewritten per release.
That is the practical reason the split is cheap here as well as correct.

## Alternatives considered

**A single installed broker holding the policy, as the runbook proposed.**
Cheaper, and it works on day one. Rejected: it ages independently of the
releases it serves, which is the ADR 0037 defect in the credential path.

**No broker; let `connect.sh` read the files under `sudo` directly.** Rejected:
the authorization decision would then live in the caller, which is the one place
it cannot live, and the `sudo` rule would have to permit reading a directory of
secrets rather than invoking one enumerated operation.

**Have the broker mint short-lived credentials instead of returning the stored
one.** Materially better, and out of scope: it needs a rotation path, an
expiry policy and a revocation story, none of which Session 4 builds. Recorded
here as the direction, not as the decision — Session 4's rotation is manual and
explicitly interrupting.

## Amended on acceptance

### 1. Point 5 is a property of the broker, not of the whole path

As proposed, point 5 said there is "no distinction in exit code between 'no such
project' and 'not yours'". Writing the trampoline made it clear that it cannot
hold where it was stated.

The trampoline reads the project's deployed document **before any policy is
consulted**, because that document is what names the release the policy lives
in. Its failures are therefore necessarily distinguishable: a project with no
`outputs.json` exits `4` naming the path, and a project that is deployed goes on
to the release. There is no ordering that fixes this. Checking authorization
first would put policy in the trampoline, which is the thing ADR 0037 forbids
and the whole reason this ADR exists.

So the claim is narrowed to where it is true, and it is true there:

* **Past the trampoline**, the broker decides authorization *before it reads
  anything about the project*. A caller with no grant is refused identically
  whether the project is deployed, released, or has never existed — same exit
  code `6`, same one-word message, which names neither the project nor the
  profile. `tests/contract/test_access_broker.py` proves the ordering the only
  way it can be proved: by authorizing successfully for a project that does not
  exist.
* **The trampoline** leaks only project-key existence, and only to an account
  already named in the `sudo -n` rule. Sudo is the coarse gate; the policy is
  the fine one.

Stated this way rather than asserted by a test on the trampoline, because a test
that claimed the indistinguishability there would be measuring the wrong file —
and the obvious way to make it pass would be to move policy into the trampoline.

### 2. The release side is `libexec/database-access-broker`

As proposed, the release side was `libexec/database-access`. The trampoline
installs as `/usr/local/libexec/agentic-postgres/database-access`, so the two
files with opposite rules — one that may hold no release-owned answer, one that
holds every one of them — would have shared a basename. That is exactly what
`project` and `project-launcher` were named apart to avoid.

The prefix rule alone would have kept the release-side file out of the installed
directory, so this is not a correctness fix. It is a legibility one, and the
kind that stops being merely cosmetic the first time somebody writes a glob.
`tests/contract/test_host_infrastructure.py` asserts that no release-side file
shares a basename with what a trampoline installs as.
