# 0084 — The pure contract lives in the build context, and the repository imports it

Status: accepted
Date: 2026-08-14
Session: 6, Run 8
Affects: ADR 0002, ADR 0078, ADR 0079, ADR 0081, and every fact two planes share

## Context

The auth service needs four things this repository already declares: the Argon2id
profile, the claim contract's shape, `verify_claims`, and the scope ceiling per
role. Each is a *fact* rather than a behaviour, each has exactly one right
answer, and each is read by two planes — the running container, and the tooling
on the deploy host that validates a manifest or renders a migration.

`compose.yaml` builds the service with `context: ./services/auth-api`, so a
`COPY` cannot reach `src/`. That is the whole constraint, and it forces a choice
this repository has strong opinions about.

Run 7 met it once, for the profile, and solved it in passing. Run 8 met it three
more times in one run — which is when a solution in passing becomes a rule.

## Decision

**A fact both planes need is declared in `services/auth-api/app/`, and
`src/agentic_postgres/` imports it.** Never the reverse, and never a copy.

`src/agentic_postgres/service_source.py` is the one loader. Four modules now go
through it:

| lives in the service | imported by | what stays behind |
|---|---|---|
| `app/profile.py` | `auth_profile` | — |
| `app/claims.py` | `jwt_claims` | `POSTGREST_ENFORCES`, `VERIFIED_ELSEWHERE`, `sql_required_claims` |
| `app/scopes.py` | `scope_registry` | the check against `capabilities.schema.json` |

**Only pure facts move, and only with no third-party import.** What stays in
`src/` is everything that is *about* those facts rather than being one:
`POSTGREST_ENFORCES` is the record of a measurement against a locked image,
`sql_required_claims` renders a migration literal, and `scope_registry` holds the
half that needs the capability schema. None of those is something the running
service does.

`test_every_service_module_the_repository_imports_needs_only_the_standard_library`
is what keeps the first half true, and it is not decoration: `config.py`
validates a manifest on a deploy host that has no `argon2`, no `pyjwt` and no
`psycopg` anywhere near it.

**Imported by name, never by path.** `service_source` puts the service root on
`sys.path` and calls `importlib.import_module`. Run 7's first attempt used
`spec_from_file_location` under a private name, which produces a **second module
object with its own classes** — and a dataclass compares
`other.__class__ is self.__class__` before anything else, so
`parse_encoded(hash) == FROZEN` was `False` for two structurally identical
profiles. A comparison that could never succeed, which is D173's shape pointing
the other way. Caught by the first test that compared across the boundary, and
`test_the_repository_and_the_service_hold_one_profile_object` asserts identity
rather than equality precisely because equality is what silently stopped meaning
anything.

## Alternatives

**Build the image from the repository root** (`context: .` with a `dockerfile:`
and a `.dockerignore`). Keeps the layout CLAUDE.md describes — pure logic in
`src/agentic_postgres/` — and is what most polyglot repositories do. Rejected on
what it drags in rather than on principle: `scope_registry` reads
`schemas/capabilities.schema.json` through `config.py`, and `config.py` imports
most of the repository. The build context would go from one directory to the
whole tree so that four modules could be copied.

**Duplicate, and tie the copies with a test.** This repository's own recorded
failure mode, twice over. D175 notes that a test comparing two constants goes
green again the moment somebody regenerates the copy. D260, one run ago, found
*three* tests in a single run that compared a value against itself — including
one whose subject was a constant duplicated for exactly this reason.

**Keep the service thin and put the checks behind an internal API.** A verifier
that asked another process whether a token's claims were well formed would make
the claim contract a network dependency of every request, and the failure mode
is a service that authenticates everything when the checker is unreachable.

## Consequences

- CLAUDE.md's "pure logic in `src/agentic_postgres/`" now has a stated exception,
  and it is narrow: a fact the image needs. Everything else is unchanged.
- The direction is one-way and must stay so. `services/auth-api/app/` may not
  import `agentic_postgres`, because the image does not contain it — a test
  asserts the absence rather than a comment asking for it.
- **`ClaimError` is no longer a `ManifestError`.** It is a plain `ValueError`
  subclass defined in the service, re-exported by `jwt_claims`, so
  `pytest.raises(jwt_claims.ClaimError)` and `except ClaimError` inside the
  service catch one object. A token is not a manifest and the old inheritance
  said it was.
- The four modules are now the first place a reader looks for the contract, and
  `src/` is where its *consequences* are recorded. That split is legible in one
  direction and not the other, which is why the docstrings on both sides name it.
