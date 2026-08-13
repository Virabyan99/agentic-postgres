# 0073 — A rendered fixture is current, or it is absent

Status: accepted
Date: 2026-08-13
Session: 5, Run 10
Amends: [0062](0062-a-required-interpolation-has-two-spellings.md)
Affects: DEP-ISO-002

## Context

Three contract modules guard themselves on `.generated/fixture-alpha-dev` and
`.generated/fixture-alpine-dev` — the Compose model, the project state roots and
the migration manifest — each the same way: skip unless the directory (or one
file in it) exists. (`test_rendered_migrations.py` reads the same tree behind the
`database` marker and asserts rather than skipping; it is left alone here.)

Run 10 narrowed `test_compose_contract.py`'s guard from module-level to
per-test, because a module-level skip is how D178 reached a live deploy. That
was right and it was not enough. **The guard asks whether the fixtures exist. It
has never asked whether they match the model they are used to test.**

The Session 5 host gate found out. `.generated/fixture-alpha-dev` there was
rendered on 2026-08-10 at `schema_version: 4`, before the PostgREST service
existed; `compose.yaml` at `dbedb72` interpolates eleven variables that render
had never heard of. `compose config` failed with eleven "missing a value"
errors, and the test reported them as an interpolation defect in the model.

The model was fine. The fixture was four schema versions old.

## Decision

**A rendered fixture is in one of three states, and only one of them is a skip.**

| State | Meaning | Behaviour |
|---|---|---|
| absent | nobody has rendered in this tree | skip — the dependency is genuinely missing |
| stale | rendered at a schema version the code has since left | **fail**, naming the version gap |
| current | rendered at `output_migrations.CURRENT_VERSION` | run |

`test_the_rendered_fixtures_are_not_stale` is the one loud failure. The
dependent tests skip citing staleness rather than each producing its own
confusing symptom — the run is already red, and eleven interpolation errors
about a healthy model are worse than one sentence saying re-render.

The state is computed in `tests/contract/rendered_fixtures.py`, one authority,
so the next module that reads a rendered fixture inherits it rather than writing
a fifth existence check.

## Why the schema version, and what it does not catch

`schema_version` is a **proxy**, and the honest thing is to say so. It is the
one number a render stamps that the code also declares, so a fixture rendered
before an outputs migration is detectable with no extra machinery — and that is
exactly the drift that occurred here, 4 against 8.

It does not catch a fixture rendered at the current schema version whose
`compose.env` is nonetheless missing a key, because a Compose variable can be
added without an outputs migration. The complete check is "every required
interpolation in `compose.yaml` has a value in the rendered `compose.env`",
which is a real test and a larger one: the required set is profile-dependent,
and some `${VAR:?required}` references are deliberately unrendered because their
values come from root-owned state at deploy time (ADR 0013). Distinguishing
those needs a second authority. **Recorded as the narrower thing it is** rather
than described as the general one — the failure mode this repository keeps
producing is a check whose name is wider than its evidence.

## Alternatives

**Render the fixtures from the gate.** Rejected for now: `--render-only`
publishes to `.generated/<key>` derived from the manifest, and the gate compares
every rendered project there pairwise for identity collisions. A gate that
renders as a side effect changes the set it is about to compare. Worth Session 6
with that ordering thought through; not worth doing quickly at the end of a run.

**Fail on absent as well.** Rejected: a clean checkout has no fixtures and has
done nothing wrong. Absence is a state of the working tree; staleness is a wrong
answer waiting to be given.

**Delete the fixtures after each render.** Rejected as backwards — it makes
every run pay to rebuild them and turns the common case into the slow one.

## Consequences

- The host must re-render before the gate: `./deploy.sh --render-only`. That is
  a new step in the operator guide and the first thing a stale run will tell you.
- Three modules stop deciding this for themselves.
- **The general lesson is the one worth carrying:** an existence check answers a
  question nobody asked. Both D178 and this were the guard being wrong about its
  own subject — first too wide, then not about the right property at all.
