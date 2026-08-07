# 0028 — Source migrations are templates; the immutable unit is the rendered payload

- **Status:** Accepted
- **Date:** 2026-08-07
- **Session:** 3
- **Affects:** DBX-MIG-002, DBX-MIG-003

## Context

Migrations have to be immutable once applied — that is the whole basis on which
a ledger of applied versions means anything. They also have to be
project-specific, because every role name, every schema-qualified owner, and the
database name itself are derived per project by Session 1's naming rules and
appear in the SQL.

Those two requirements point in opposite directions. A file committed to the
repository cannot be immutable *and* contain `alpha_dev_object_owner`, because
the same file has to produce `beta_dev_object_owner` for the other project.

So there are two artifacts, and the decision is which one immutability attaches
to. Checksumming the source template means two projects applying the same
migration record the same checksum, and a change to the *rendering* — a naming
rule, a placeholder's meaning — passes unnoticed because the source bytes did
not move. Checksumming the rendered payload means the recorded checksum
describes the bytes PostgreSQL actually executed.

The renderer's design is settled by a failure this repository already had.
In Run 7 of Session 2, `render-config.py` performed a substitution that also
matched the comment documenting the placeholder, and produced a Traefik file
that Traefik silently discarded. The lesson is not "be careful with regexes"; it
is that a substitution mechanism powerful enough to surprise you will.

## Decision

**The immutable unit is the rendered payload.** `migrations/released.lock.json`
records the checksum of what is applied, per project, not of the template.

`migrations/manifest.json` is the ordered source of record for versions and
template paths. The templates live under `migrations/templates/`.

The renderer is purpose-built and deliberately incapable:

- it substitutes only **typed placeholders from a fixed schema** — identifiers
  and literals, each declared with its type;
- identifiers are validated against the naming rules and quoted as identifiers,
  never interpolated as text;
- there is **no control flow**, no conditional, no loop, no arbitrary
  expression, and no partial-application syntax;
- there is **no secret placeholder**. A placeholder whose name matches the
  sensitive-key policy (ADR 0008) is a render-time failure, not a redaction;
- there is **no current-deployment metadata** — no timestamp, no commit, no
  hostname, nothing that would make two renders of the same input differ;
- an unknown placeholder is a failure, and so is a declared placeholder that
  the template never uses.

A minimal renderer is preferred over a general template engine for the reason
above: the failure mode of a general engine is a file that renders to something
plausible and wrong.

`bin/migrate.sh freeze-lock` produces `released.lock.json` from a clean tree.
It is reviewed and committed **before** the final gate. The gate verifies it and
never creates or rewrites it.

## Consequences

The preflight compares five things and refuses on any disagreement: the applied
dbmate versions, the database ledger, the source manifest, the released lock,
and the currently rendered set. Five sources is more than strictly necessary to
detect a single edit; it is what distinguishes *which* of history rewrite,
context change, and direct database alteration occurred, which is what the
operator needs in order to act.

An applied migration cannot be edited. The remedy for a mistake is a new
migration. The `down` block raises `AP900` deliberately: released platform
migrations are fix-forward only.

Rendering must be deterministic, and this is testable offline with no cluster:
render twice, compare bytes. That makes `DBX-MIG-002` an offline claim.

Enforced by:

- `DBX-MIG-002` — rendered migrations are deterministic and checksum-consistent
  with source (Run 4)
- `DBX-MIG-003` — an applied migration cannot be silently edited, removed, or
  reordered (Run 4, mutation cases; Run 8 against a live ledger)

## Alternatives considered

**Checksum the source template.** Simpler, and it is what most migration tools
do because most migration tools do not render. Here it would mean a change to a
naming rule silently alters what every project executes while every recorded
checksum stays identical — the exact class of defect this project keeps
producing.

**Commit the rendered migrations per project.** Makes the applied bytes
reviewable in git. It also puts `project.alpha.yaml`-derived identifiers into
source control for every project that ever exists, and those manifests are
gitignored operator inputs precisely so that they do not appear there.

**Use a general template engine (Jinja2 or similar).** Well-tested, familiar,
and already a transitive dependency. Its power is the problem: conditionals and
filters in migration SQL make the rendered result a function of logic that no
checksum covers until after it has run.

**Render at apply time inside the container and never store the payload.** Saves
an artifact. It also means nothing can be checked before the SQL reaches the
database, which removes every offline proof.
