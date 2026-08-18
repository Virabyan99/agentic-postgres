"""The object key: one derivation, and the validator that does not re-derive it.

ADR 0102. The key has two halves with one authority each. The **prefix** is
`naming.storage_object_prefix`'s, read from the deployed document and never
re-derived here. The **suffix** is generated per upload intent, which can only
happen inside this container -- so it lives here, in the build context, and
`src/agentic_postgres/` reaches it through `service_source.load`, exactly as the
Argon2 profile and the scope ceiling already do (ADR 0084).

    object key = <storage_prefix> + "v1/" + <uuid4>

**Standard library only**, for the reason `profile.py` gives: two planes need
this and only one of them can have the service's dependencies installed.

**The key is not the object id, and they are independent random values.** The id
appears in request paths and is therefore known to any caller holding one; the
key appears only inside a presigned URL. Coupling them would let a caller
construct the key from the id -- not by itself an authorization failure, since
reaching the object still needs a signed URL, but the two have different
exposure and no reason to be equal.
"""

from __future__ import annotations

import re
import uuid

#: The layout generation. A key records which layout produced it, so a later
#: change is a new value here rather than a migration over stored strings --
#: keys are immutable once an object exists, and a bucket may hold both.
KEY_VERSION = "v1"

#: What a generated suffix looks like: the version segment and a canonical
#: lowercase uuid4. Written out rather than assembled from KEY_VERSION and a
#: uuid pattern, because a validator built from the same expression as the
#: generator agrees with the generator by construction and measures nothing
#: (D173). This is the shape as a *reader* would recognise it.
_SUFFIX = re.compile(r"\Av1/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")


def object_key(prefix: str) -> str:
    """Compose one object key over a prefix the caller was handed.

    `prefix` comes from the deployed document by way of `APG_STORAGE_PREFIX`.
    This function neither derives it nor validates its provenance; what it
    guarantees is the half it owns. There is deliberately no constant spelling
    `objects/` anywhere in this service.

    `uuid4` is `os.urandom`-backed, so the suffix carries 122 unguessable bits.
    """
    return f"{prefix}{KEY_VERSION}/{uuid.uuid4()}"


def is_derived_key(prefix: str, candidate: str) -> bool:
    """Does `candidate` have the shape `object_key(prefix)` produces?

    `STO-KEY-001` is "the generated key matches the derived format", and a proof
    that re-derives the format to compare against is a tautology in one
    direction -- D173, where `probe not in {api.notes, ...}` could never fail.
    So this checks the prefix by string equality and the suffix against a
    pattern written independently of the generator, including uuid4's version
    and variant nibbles. A generator switched to `uuid1` would be caught here;
    one switched to a different prefix would be caught by the first clause.
    """
    if not prefix or not candidate.startswith(prefix):
        return False
    return bool(_SUFFIX.match(candidate[len(prefix) :]))
