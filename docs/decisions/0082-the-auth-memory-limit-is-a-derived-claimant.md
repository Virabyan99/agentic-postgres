# 0082 — The auth service's memory limit is a derived claimant

Status: accepted
Date: 2026-08-14
Session: 6, Run 7
Affects: D234, and every project manifest that enables the application API

## Context

The runbook §4.10 bounds Argon2 to "no more than two concurrent operations per
container" and reserves "at least 128 MiB for two concurrent 64 MiB hashes";
§15.2 sets a 384 MiB memory limit. Three numbers, in two documents, with one
true relationship between them and nothing computing it — which D234 recorded as
the shape this project keeps failing on.

The failure it leaves open is specific: raise `hash_concurrency` without raising
the limit and the container is killed by the OOM killer at the first burst of
logins. The host has no swap, so the OOM killer is the only backstop, and it does
not choose politely — it can take Traefik, which drops every project's ingress at
once.

**Measured in Run 7**, one profile per process, with a no-hash control:

| what | resident delta |
|---|---|
| baseline, no hash (the control) | **0.0 MiB** |
| 1 concurrent hash at the frozen profile | 67.1 MiB |
| 2 concurrent | 131.1 MiB |
| 4 concurrent | 259.0 MiB |
| 2 concurrent at `m=32768` | 67.1 MiB |
| 2 concurrent at `m=19456,t=2` | 41.1 MiB |

Linear in concurrency, and equal to `concurrency × memory_cost` plus about
3 MiB. The first attempt at this measurement reported 87 MiB for every row,
because `ru_maxrss` is a high-water mark and the mark had been set by hashes run
earlier in the same process — an uninformative measurement with plausible
numbers, which is why the control is in the table.

And the constant term, measured by importing one layer at a time: 12.8 MiB bare,
15.6 with argon2, 26.0 with PyJWT, 39.1 with psycopg and its pool, 49.6 with
pydantic, 54.4 with FastAPI, **60.9 with uvicorn and an application object**.

## Decision

**The auth container's memory limit joins the derived budget as a named
claimant**, the way ADR 0070 made the connection budget a division rather than a
set of independent grants.

    floor = hash_concurrency × memory_cost + process_overhead
          = 2 × 64 MiB + 96 MiB
          = 224 MiB

`api.app.memory_limit_mb` is declared in the manifest, defaults to 384, and a
manifest declaring less than the floor **fails validation** — offline, at render
time, with no host involved. The relation is a `CROSS_FIELD_RELATIONS` entry and
appears in the generated bounds documentation.

**The relation lives in `services/auth-api/app/profile.py`**, beside the profile
it is a relation about, and `agentic_postgres.auth_profile` imports that module
rather than restating it. Two files holding the same constant, with a test
comparing them, is not good enough here: a test that compares two constants goes
green again the moment somebody regenerates the copy, which is D175's recorded
and unfixed failure mode.

**Process overhead is charged at 96 MiB against a measured 60.9.** The measured
figure is an idle process with no connections open, no request buffers and no
schema cached. The direction that costs a redeploy is cheaper than the direction
that costs an OOM kill.

**The check is unconditional** — it runs for a project that declares no
`api.app` section and for one that declares it disabled. This is D256's
correction applied at the point of writing rather than rediscovered: the
renderer publishes `AUTH_MEMORY_LIMIT` whether or not the service is enabled, so
a check that ran only for an enabled service would disagree with the file that
starts the container.

**`hash_concurrency` is not a manifest field.** It is frozen beside the profile,
because a deployment that could raise it without raising the limit is exactly the
failure this decision exists to prevent, and making it configurable would put the
adjustable end of the relation in the hands of the person least placed to measure
it.

## Alternatives

**Type 384 MiB into the Compose file, as the runbook does.** It is probably the
right number — the floor is 224 and 384 leaves 160 MiB for connections and
request buffers. What it does not do is move when the profile does, and the
profile is the thing a future session is most likely to change.

**Charge the auth service against `HOST_MEMORY_GUARDRAIL_MB`.** That guardrail
is what one host may commit to *PostgreSQL clusters*, and its arithmetic is
about shared buffers and per-backend anonymous memory. Adding a service to it
would make one number mean two things. The auth limit is a per-project container
limit and is bounded on its own terms; a host-level total across all services is
a real gap and is recorded as an open item rather than solved here.

**Derive the limit instead of validating it.** Tempting, and wrong for the same
reason `database.memory_limit_mb` is declared rather than derived: the limit is
a statement about what the operator is willing to spend on this project, and the
repository's job is to refuse a figure that cannot work, not to choose one.

## Consequences

- A manifest that raises hashing cost without raising the limit is refused
  offline instead of being killed on a host.
- The floor moves if the profile moves, automatically, because both come from
  one module.
- **The host figure is unmeasured.** Everything above was measured on the
  development machine — same interpreter, same wheels, same architecture, and a
  materially quieter box. The relation is a property of Argon2 and will hold; the
  *absolute timing* (133 ms per hash, 118 ms per verification, steady state) will
  not, and no proof has run on the VPS. Recorded as an unmeasured boundary rather
  than assumed, which is what §3's feasibility item asked for and what Run 10 or
  11 must close.
