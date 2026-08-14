# 0081 — The frozen Argon2id profile is checked on the stored hash

Status: accepted
Date: 2026-08-14
Session: 6, Run 7
Affects: SEC-CRED-001, SEC-CRED-002, and every credential this product stores

## Context

The auth service hashes passwords with Argon2id at a fixed profile. "Fixed" is
easy to write and, as measured, not something the library provides.

**`PasswordHasher.verify()` returns `True` for a hash produced with a weaker
profile.** Measured against the locked argon2-cffi 25.1.0:

    weak = PasswordHasher(type=Type.ID, memory_cost=8192, time_cost=1, parallelism=2)
    stored = weak.hash(password)

    PasswordHasher().verify(stored, password)            -> True
    PasswordHasher().check_needs_rehash(stored)          -> True

The encoded hash carries its own parameters, so the library *knows* the profile
does not match. It reports the mismatch through `check_needs_rehash` and
verifies anyway. That is the right default for a library whose users migrate
between profiles. It is the wrong behaviour for a service with one profile:
a credential written at `m=8192,t=1,p=2` — by an earlier version, a restored
backup, a migration script, or anything at all that is not this service — would
keep authenticating for as long as it existed, and nothing would fail.

The second measurement is what makes the first one fixable. **The encoded hash
records the whole profile** and it can be read back:

    $argon2id$v=19$m=65536,t=3,p=1$yIRmpJv6EumBRkIUR4O8AQ$iIp1p4UA...

Variant, version, memory cost, time cost, parallelism, and — from the base64
field widths — the salt and hash lengths. Control: a hash produced at a
different profile reads back differently, and `argon2i`, `argon2d` and
`argon2id` are distinguishable by their prefixes.

## Decision

**The profile is enforced on the way in, by reading the stored hash's own
parameters before the password is checked against it.**

`app/profile.py` declares the profile and a `parse_encoded` that reads a PHC
string. `Hasher.verify` parses the stored hash first; if the recorded profile is
not the frozen one it raises `StoredHashRejected` and does not attempt
verification.

The profile:

| Field | Value |
|---|---|
| variant | `argon2id` |
| version | 19 |
| `memory_cost` | 65536 KiB (64 MiB) |
| `time_cost` | 3 |
| `parallelism` | 1 |
| `hash_len` | 32 bytes |
| `salt_len` | 16 bytes |

**`parse_encoded` is hand-written and does not call argon2.** `argon2.
extract_parameters` exists, works, and is deliberately not what proves the
profile. SEC-CRED-002 says the profile is read back *from the encoded hash*, and
asking argon2 what argon2 just did is the same authority twice: a library that
silently ignored a constructor argument would produce a hash and a readback that
agree with each other and disagree with the profile.
`test_the_hand_written_parser_agrees_with_the_library_it_does_not_use` is the
control — it compares the two readers across three profiles, so a parser that
returned the frozen constant unconditionally fails.

**`matches` is equality, not "at least as strong as".** A stored hash produced
with *stronger* parameters is also refused. Accepting it would mean the service
has two profiles, which is the state this decision exists to make unreachable by
accident. Upgrading the profile is a rehash, and a rehash is a deliberate act
with its own ADR.

**`parallelism = 1`**, which is neither pwdlib's default (4) nor the runbook's
implied 2. `p` is *lanes within a single hash*, not throughput: raising it
spends more of the host's cores on one login without changing what a login costs
in memory, on a 4 GB VPS already running two PostgreSQL clusters, two poolers,
two PostgREST instances, two documentation services and an edge. With `p = 1`,
one login is one core's work and `hash_concurrency` is the only knob — which is
what ADR 0082's relation needs in order to be a relation. `p` is also recorded
in every hash the profile produces, so changing it later invalidates the frozen
check for every credential already stored.

**A profile mismatch raises rather than returning `False`.** "This hash was
written by something else" is an operational fault; reporting it as a wrong
password would hide a real problem behind thousands of failed logins, which is
the failure mode that takes longest to notice. The dummy verification still runs
first, so the fault is not also a timing signal that distinguishes one stored row
from another.

## Alternatives

**Rely on `check_needs_rehash` and rehash on next login.** This is the library's
intended path and it is right for a service that migrates profiles. It requires
accepting the weak hash once — which is precisely the moment being defended
against, because the attacker who planted it only needs the once.

**Compare the constructor's arguments.** Free, and measures nothing: it asserts
what was asked for, not what was done, and it cannot see a hash that arrived
from anywhere other than this process.

**Store the profile in a column beside the hash.** Two authorities for one fact,
and the second one is writable by whatever wrote the row.

## Consequences

- A credential written under any other profile cannot authenticate. If the
  profile is ever changed, every stored hash must be re-derived from a password
  at login time under an explicit migration path, and there is none today.
- `pwdlib` is pinned in `versions.in.yaml` and is **not used**. Its
  `Argon2Hasher` defaults to `parallelism=4` and its value is multi-algorithm
  migration, which a service with one frozen profile does not have. The pin is a
  candidate, not a claim about the image; the Dockerfile does not install it.
- The hand-written parser is a second implementation of a format this service
  does not own. It is ~40 lines, it is exercised against the library's own reader
  for three profiles, and it is the only thing that makes SEC-CRED-002 a
  measurement rather than an assertion.
