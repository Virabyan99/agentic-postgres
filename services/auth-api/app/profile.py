"""The frozen Argon2id profile, and a reader for it that argon2 did not write.

**Why this module imports nothing but the standard library.** Two callers need
the profile and only one of them can have `argon2` available:

* `hashing.py`, inside the service image, which applies it;
* `src/agentic_postgres/config.py`, on the deploy host, which checks the
  manifest's memory relation against it (ADR 0082).

A number duplicated in those two places is the shape this repository keeps
failing on -- `memory_cost = 65536` and `hash_concurrency = 2` and a container
limit are three numbers with one true relationship between them (D234). So the
profile is declared once, here, in the build context the image is built from,
and `agentic_postgres.auth_profile` loads *this file* by path rather than
restating it.

**Why the parser is hand-written.** `argon2.extract_parameters` exists and works
-- measured in Run 7, and it reads back every field including the type and the
version. It is deliberately not what proves the profile. SEC-CRED-002 says the
profile is read back *from the encoded hash*, and asking argon2 to tell you what
argon2 just did is the same authority twice: a library that silently ignored a
constructor argument would produce a hash and a readback that agree with each
other and disagree with the profile. `parse_encoded` below reads the `$`-
delimited PHC string with `str.split`, so the two answers come from two places.

**The measurement that makes this module load-bearing** (Run 7, argon2-cffi
25.1.0): `PasswordHasher(...).verify()` returns True for a hash produced with a
*weaker* profile. `check_needs_rehash` reports the mismatch and nothing acts on
it. So "the profile is frozen" is not a property verification gives you -- a
credential stored at `m=8192,t=1,p=2` would keep authenticating for as long as
it existed. `FROZEN.matches` is what the service checks before it trusts a
stored hash, and ADR 0081 is why that check exists at all.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The Argon2 variant. `id` is the hybrid -- data-independent in the first pass
#: and data-dependent afterwards -- which is what RFC 9106 recommends for
#: password hashing, and the only one of the three this service will produce or
#: accept. It is part of the profile rather than assumed because the encoded
#: string records it and a reader that ignored it would accept an `argon2i`
#: hash as though the frozen profile had been applied.
ARGON2_TYPE = "argon2id"

#: The Argon2 algorithm version, decimal, as the encoded string spells it
#: (`v=19`, which is 0x13). Pinned for the same reason as the variant: an older
#: version number in a stored hash means the value was produced by something
#: other than this service.
ARGON2_VERSION = 19


@dataclass(frozen=True, slots=True)
class Argon2Profile:
    """Every parameter the encoded hash records, and nothing that it does not.

    The fields are exactly the ones a PHC string carries, so `matches` can be a
    comparison rather than a judgement about which differences are important.
    """

    type: str
    version: int
    memory_cost_kib: int
    time_cost: int
    parallelism: int
    hash_len: int
    salt_len: int

    def matches(self, other: Argon2Profile) -> bool:
        """Exact equality on every field.

        Not "at least as strong as". A stored hash produced with *stronger*
        parameters is also not this profile, and treating it as acceptable
        would mean the service has two profiles -- which is the state this
        module exists to make impossible to reach by accident. Upgrading is a
        rehash, and a rehash is a deliberate act with an ADR behind it.
        """
        return self == other


#: The profile. Measured on the development machine in Run 7 at 133 ms per hash
#: and 118 ms per verification, steady state, and 67.1 MiB resident per
#: concurrent hash -- `memory_cost` plus about 3 MiB, linear in concurrency.
#:
#: `parallelism = 1`, which is neither pwdlib's default (4) nor the runbook's
#: implied 2, and the reason is that `p` is *lanes within a single hash*, not
#: throughput. Raising it spends more of the host's cores on one login without
#: changing what a login costs in memory, on a 4 GB VPS that is already running
#: two PostgreSQL clusters, two poolers, two PostgREST instances, two
#: documentation services and an edge. With `p = 1` one login is one core's
#: work and `hash_concurrency` is the only knob, which is what ADR 0082's
#: cross-field relation needs in order to be a relation rather than a guess.
#:
#: `p` is also recorded in every hash this profile produces, so changing it
#: later invalidates the frozen-profile check for every credential already
#: stored. That is an argument for choosing it once, deliberately, here.
FROZEN = Argon2Profile(
    type=ARGON2_TYPE,
    version=ARGON2_VERSION,
    memory_cost_kib=65536,
    time_cost=3,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

#: How many hashes may be in flight in one container at once. This is the second
#: term of ADR 0082's relation and it is here rather than in the manifest for
#: the reason the profile is: a deployment that could raise it without raising
#: the memory limit would be a deployment that can be made to OOM by logging in.
#: The manifest declares the *limit*; validation refuses a limit this does not
#: fit.
HASH_CONCURRENCY = 2

#: What the service's own process costs before it hashes anything, in MiB.
#: Measured in Run 7 by importing one layer at a time: 12.8 bare, 15.6 with
#: argon2, 26.0 with PyJWT, 39.1 with psycopg and its pool, 49.6 with pydantic,
#: 54.4 with FastAPI, 60.9 with uvicorn and an application object. Charged at 96
#: rather than 61 because the measured figure is an idle process with no
#: connections open, no request buffers and no schema cached, and the direction
#: that costs a redeploy is cheaper than the direction that costs an OOM kill.
#:
#: Measured on the development machine, not on the host. The host figure is
#: expected to be close -- the same interpreter, the same wheels, the same
#: architecture -- but it is *unmeasured*, and this comment says so rather than
#: implying the number was taken there.
PROCESS_OVERHEAD_MB = 96


def parse_encoded(encoded: str) -> Argon2Profile:
    """Read a PHC-format Argon2 string with the standard library only.

    The format is `$type$v=N$m=N,t=N,p=N$salt$hash`, base64 without padding for
    the last two fields. Raises `ValueError` on anything that is not exactly
    that -- including a string with the right shape and an unexpected parameter
    order, because `m,t,p` is what the format specifies and a hash spelling them
    differently was not produced by the library this service uses.
    """
    if not isinstance(encoded, str):
        raise ValueError("an encoded hash is a string")
    parts = encoded.split("$")
    # A leading empty field, then five: type, version, parameters, salt, hash.
    if len(parts) != 6 or parts[0] != "":
        raise ValueError(f"not a PHC-format hash: {len(parts)} fields")

    _, variant, version_field, parameter_field, salt, digest = parts

    if not version_field.startswith("v="):
        raise ValueError("no version field")
    try:
        version = int(version_field[2:])
    except ValueError as exc:
        raise ValueError("version is not an integer") from exc

    names = ("m", "t", "p")
    pairs = parameter_field.split(",")
    if len(pairs) != len(names):
        raise ValueError(f"expected {len(names)} parameters, found {len(pairs)}")
    values: list[int] = []
    for pair, name in zip(pairs, names, strict=True):
        prefix = f"{name}="
        if not pair.startswith(prefix):
            raise ValueError(f"expected parameter {name!r}, found {pair!r}")
        try:
            values.append(int(pair[len(prefix) :]))
        except ValueError as exc:
            raise ValueError(f"parameter {name!r} is not an integer") from exc

    return Argon2Profile(
        type=variant,
        version=version,
        memory_cost_kib=values[0],
        time_cost=values[1],
        parallelism=values[2],
        # Lengths are the DECODED byte counts, not the base64 field widths. The
        # obvious `len(salt)` is 22 for a 16-byte salt and would make every
        # comparison against FROZEN fail for a reason that has nothing to do
        # with the profile.
        hash_len=_b64_decoded_length(digest),
        salt_len=_b64_decoded_length(salt),
    )


def _b64_decoded_length(field: str) -> int:
    """How many bytes an unpadded base64 field decodes to.

    Computed rather than decoded: this module may not import `base64`'s
    validation behaviour into the profile check, because a field that is not
    valid base64 is a malformed hash and should raise here rather than three
    frames away. Four characters carry three bytes; a remainder of 2 carries 1
    and a remainder of 3 carries 2. A remainder of 1 is impossible.
    """
    whole, remainder = divmod(len(field), 4)
    if remainder == 1:
        raise ValueError("base64 field has an impossible length")
    return whole * 3 + (remainder - 1 if remainder else 0)


def hash_memory_budget_mb(concurrency: int = HASH_CONCURRENCY) -> int:
    """What one auth container must be allowed to hold, in MiB.

    `concurrency x memory_cost` plus the process overhead, which is ADR 0082's
    relation written once so the manifest validator and the renderer cannot
    each have their own version of it. Measured linear in Run 7: 67.1 MiB at
    concurrency 1, 131.1 at 2, 259.0 at 4, against a no-hash control that moved
    the resident figure by 0.0.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    return concurrency * FROZEN.memory_cost_kib // 1024 + PROCESS_OVERHEAD_MB
