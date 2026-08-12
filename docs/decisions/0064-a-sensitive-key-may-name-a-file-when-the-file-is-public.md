# 0064 — A sensitive-looking key may name a file, when the file is public and the path is declared

Status: accepted
Date: 2026-08-12
Session: 5, Run 9
Amends: [0008](0008-sensitive-key-policy.md)
Affects: SEC-SECRET-001

## Context

`test_no_service_takes_a_secret_through_the_environment` has held since Session 2:
an `environment:` entry is visible in `docker inspect` forever, so no service may
receive one whose key is sensitive under ADR 0008's denylist.

Run 9 adds `PGRST_JWT_SECRET` to the PostgREST service. `is_sensitive_key`
rejects it — it ends in `_secret` — and the test fires, correctly, on the rule as
written.

The name is not ours to choose. PostgREST's configuration key is `jwt-secret`,
so the environment variable is `PGRST_JWT_SECRET`, and the service is configured
**entirely** through the environment on purpose: that is what makes `postgrest
--ready` usable as a healthcheck at all (D153 — the probe is a client that reads
its own configuration, and only because the configuration lives in the
environment is the probe's configuration the service's). Moving to a config file
to dodge the name would trade a naming collision for a healthcheck that proves
nothing.

The value is `@/etc/postgrest/jwks.json`. PostgREST's `@` prefix means *read this
from a file*. What `docker inspect` shows is a path; what the path names is a
modulus, an exponent, an algorithm and an RFC 7638 thumbprint, written `0444`
because it is public verification material (ADR 0051). Nothing in it can sign.

So the property the test protects is not violated, and the rule that expresses
that property does not distinguish a **value** from a **reference**.

ADR 0008 already drew this distinction once, at the key level: `password_secret_ref`
is allowed because it is a reference, and its allowance is asserted in
`test_the_key_scan_would_actually_reject_something`. This is the same distinction
one level down, at the value.

## Decision

**A sensitive-named environment key is permitted only when its value is a file
reference to a declared public path.** Three conditions, all required:

1. the value begins with `@` — a reference, not a value;
2. the referenced path is in `PUBLIC_REFERENCE_PATHS`, a closed enumeration
   derived from `runtime_override`, not a name-based exemption;
3. the referenced path is not under `/run/secrets`, which is where materialized
   secrets are mounted.

Anything else remains an offender, as before.

**This is a relaxation in one direction and a tightening in two**, and the
tightenings are the reason it is acceptable. The old rule inspected only the
key's *name*: a sensitive key was refused and every other key's value went
unexamined against this rule. The replacement additionally requires that a
permitted key's value be a reference at all, and that the path be one this
repository declares — so a second `@` reference, to any other path, fails. A
future service pointing `PGRST_JWT_SECRET` at `/run/secrets/anything` fails on
condition 3 even though its key would have been permitted by name.

The rejected alternatives:

**Exempt `PGRST_JWT_SECRET` by name.** One line, and it makes the rule "this
variable is fine because we said so". The next such variable gets the same line
and nobody re-derives whether the file behind it is public.

**Remove `_secret` from the denylist.** It would silence this and every future
`*_secret` key, which is the opposite of what ADR 0008 is for.

**Rename the variable.** Not available: PostgREST reads `PGRST_JWT_SECRET` and
nothing else.

## Consequences

- `SEC-SECRET-001`'s guarantee is unchanged in substance: no service receives
  secret *material* through its environment. What is now stated precisely is
  that a path to a public file is not material.
- Adding a second public reference means adding its path to
  `PUBLIC_REFERENCE_PATHS`, in the module that also declares the mount — so the
  path a service reads and the path this rule permits cannot drift apart.
- `test_no_verification_key_is_configured_yet` is retired by this run rather
  than amended. Its own docstring says so: "This test goes red on the day the key
  is added, which is the day the run that renders the JWKS has to say so." It is
  replaced by an assertion about what the key *is*, which is the stronger claim —
  an absence can be satisfied by a typo in the variable's name.
