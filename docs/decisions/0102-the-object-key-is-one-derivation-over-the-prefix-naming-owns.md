# 0102 — The object key is one derivation over the prefix `naming` owns

Status: accepted
Date: 2026-08-15
Session: 7, Run 1
Settles: D315
Extends: [0002](0002-single-authority-derivation.md), [0084](0084-the-pure-contract-lives-in-the-build-context.md)

## Context

The runbook's §7.1 introduces an object key format, `objects/v1/<yyyy>/<mm>/<uuid>`,
as a constant of the storage service. D315 recorded the collision: a `storage:`
section **already exists** in `schemas/project.schema.json` and carries a
`prefix`, described as *"Relative object prefix ending in '/'. Defaults to
`objects/{project_key}/`."*

Both strings begin `objects/`, both name where a project's objects live, and
neither knows about the other. That is D177's shape — the documentation route
derived twice, `/docs` in one place and `/docs/rest` everywhere it was measured,
with the copy carrying a comment saying it was "kept in step" being the one that
had not drifted.

**The prefix half already has an authority, and it was verified rather than
assumed.** The schema describes a default, and D276's rule is that a declaration
saying a value is derived from something is a reason to grep for the deriver.
The deriver exists: `naming.derive` reads

    storage_bucket = r2_bucket(storage_bucket if storage_bucket else key)
    storage_prefix = (storage_prefix if storage_prefix else f"objects/{key}/")

so the manifest's `bucket` and `prefix` are **overrides of a derivation**, not
inputs to one, and `naming.py` is already ADR 0002's single authority for both.
Nothing is wrong here and nothing needs fixing. What is missing is the other
half: the per-object suffix, which no code derives because no code has needed
one.

**The suffix cannot live in `naming.py`.** It is generated per upload intent, by
the storage runtime, inside a container whose build context cannot reach `src/`
— ADR 0084's constraint, unchanged.

## Decision

**One key, two halves, one authority each, and they compose in one function.**

    object key = <storage_prefix> + "v1/" + <uuid4>

- **The prefix** is `naming`'s, read from the deployed document. The runtime
  never derives it and never reads the manifest.
- **The suffix** is derived by `object_key()` in
  `services/auth-api/app/object_keys.py` — standard library only, imported by
  `src/agentic_postgres/` through `service_source.load`, exactly as the Argon2
  profile, the claim contract and the scope ceiling already are.
- **The composition is that one function**, which takes the prefix as an
  argument. There is no second place that concatenates a prefix and a suffix,
  and no constant anywhere spelling `objects/`.

`object_keys.py` also exports the **validator** — given a prefix, does this
string have the derived shape — because `STO-KEY-001` is *"the generated key
matches the derived format"* and a proof that re-derives the format to compare
against is the tautology D173 records.

**What the layout deliberately does not carry.**

**No date partition.** The runbook's `<yyyy>/<mm>/` is an S3-era answer to key
prefixes as hot partitions, and it buys nothing here for a second reason that is
this project's own: cleanup is **metadata-driven and never lists the bucket**
(plan §4.5), so there is no listing operation for a date prefix to narrow. What
it would add is a creation date, encoded in a string, beside the row that already
holds the real one — a second authority for a timestamp, and one that leaks into
a presigned URL.

**The key is not the object id.** They are independent random values. The object
id appears in request paths (`/objects/{id}/download-url`) and is therefore known
to any caller who holds one; the key appears only inside a presigned URL. Making
them equal would mean a caller could construct the key from the id. That is not
by itself an authorization failure — reaching the object still requires a signed
URL, which is an authorization decision made at issue time — but the two values
have different exposure and there is no reason to couple them. `uuid4` is
`os.urandom`-backed, so the key is 122 unguessable bits.

**`v1/` is a layout version**, and it is the authority for one: a later layout is
distinguishable from this one by inspection, and the validator can accept both
during a transition. It costs three characters and it is the difference between a
migration that can tell old from new and one that cannot.

## Alternatives

**Put the whole key format in the manifest, as a template string.** Rejected:
the manifest is an operator input and a key layout is not an operator decision.
It would also make the format per-project, so two projects could disagree about
what a key looks like and every proof about the format would have to be
parameterised by manifest.

**Put the whole key in `naming.py` and pass the finished key to the runtime.**
Rejected: the key is generated per intent, at request time, and `naming` is
render-time. The runtime would be asking the repository for a value on every
upload.

**Derive the suffix from the object id.** One value instead of two, and the key
becomes reconstructible for debugging. Rejected above: different exposure, no
compensating benefit, and the "reconstructible for debugging" property is one an
operator command can provide from the row without the coupling being permanent.

**Keep both layouts — the manifest's `prefix` for the bucket layout and the
runbook's template for the object.** Rejected on D177. Two derivations of one
string agree until the day one of them moves, which is the only day it matters,
and the copy that carries a comment about being kept in step is not reliably the
one that drifted.

**Drop the manifest's `prefix` override and derive it unconditionally.** Tidier
— one fewer way for two projects to collide. Rejected as out of scope and
regressive: the override is published, the fixtures use it, and removing an
operator input to simplify a derivation this ADR is not otherwise touching is a
change with no measurement behind it.

## Consequences

- `services/auth-api/app/object_keys.py` is the third module `service_source`
  loads. `test_every_service_module_the_repository_imports_needs_only_the_standard_library`
  covers it with no new mechanism.
- The runtime receives `storage.prefix` from the deployed document and passes it
  in. It holds no default for it: a missing prefix is a startup failure, not a
  fallback to `objects/`.
- `STO-KEY-001` is provable in two halves — the request model admits no key
  field, and a generated key satisfies the validator — with neither half
  re-deriving the format it is checking.
- Objects written under a future layout are distinguishable from these by their
  second segment, and the validator is where that transition is expressed.
