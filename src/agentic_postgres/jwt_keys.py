"""The issuer's public half: JWKs, thumbprints, and a rotation nobody can rush.

ADR 0051 decided the shape and ADR 0055 decided the storage. What is here is
everything about that key that can be computed without holding it: a public JWK
from a modulus and an exponent, an RFC 7638 thumbprint, a verification-only JWKS
that refuses private material, and the **four-phase** rotation state machine
with the deadline the deployed document records.

Four phases, not two, and ADR 0088 is why. The two-phase pair this replaced
(`begin_rotation`, `complete_rotation`) published the second key and switched
signing in one step, so there was no moment at which anything could check that
the verifiers had the new key -- and D235 found that neither function had ever
been called, which is the only reason that was never a live defect.

    prepare      publish both keys; the ACTIVE key does not move
    acknowledge  record, per consumer, the digest that consumer has LOADED
    promote      refused unless every verifier has acknowledged; switches signing
    retire       refused before the deadline; publishes the active key alone

The step that makes it work is the third one's refusal, and the reason it has to
exist is measured: a running PostgREST **never re-reads its key set**. Writing a
file is not propagation, so "every verifier has the new key" cannot be inferred
from anything the issuer did -- it has to be recorded from the verifiers.

**Nothing here reads the private key and nothing here signs.** The private key is
a PEM that only `openssl` handles (ADR 0055), and the modulus and exponent this
module builds a JWK from are read out of `openssl rsa -noout -modulus -text` by
the caller. That split is what makes every rule below testable with no key, no
host and no container -- which matters, because the rules are the security
properties.

Four of them are worth naming here rather than leaving in a docstring below:

* **A public JWK carrying `d` is a private key with a misleading label.** The
  refusal is by parameter name against the complete RFC 7518 set, and it is
  asserted against a deliberately malformed input rather than trusted.
* **`kid` is derived, not chosen.** RFC 7638 makes it a function of the key, so
  two keys cannot share one and one key cannot have two. A supplied `kid` that
  disagrees with the thumbprint is refused rather than preferred.
* **A rotation has a deadline and the deadline is a value.** Retirement removes
  the retiring key and may not run early. "After the tokens have expired" as a
  sentence is a rotation that never completes; as `retire_after` it is a
  comparison.
* **Promotion is blocked on a record, not on a wait.** "Give it a minute for the
  verifiers to pick it up" is the same sentence in the other direction, and a
  minute is not a fact about anything. `verifier_acknowledgements` names each
  verifier and the digest it holds, and a name missing from that map is the
  reason a promotion is refused.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

#: Every private RSA parameter RFC 7518 defines. A public JWK carrying any of
#: them is not a public JWK. `oth` is in the list although it appears only in
#: multi-prime keys, because "we do not generate those" is a statement about the
#: generator and this is a check on an input.
PRIVATE_JWK_PARAMETERS = ("d", "p", "q", "dp", "dq", "qi", "oth")

#: The members an RSA public JWK carries here, and the exact set. `alg` and `use`
#: are pinned rather than optional so that a verifier reading this document
#: cannot be talked into a different algorithm by the document itself.
PUBLIC_JWK_MEMBERS = frozenset({"kty", "n", "e", "alg", "use", "kid"})

#: RS256 and only RS256 (ADR 0051). Asymmetric, so a verifier holds nothing that
#: can sign; and the one algorithm every JWT implementation supports without
#: configuration, which matters for a key that exists to be verified elsewhere.
ALGORITHM = "RS256"

#: At most two keys verify at once: the active one, and during a rotation the one
#: retiring. Two is a ceiling rather than a convention because an unbounded
#: verification set is a set nobody ever retires from -- every key stays valid
#: because removing one is always something that can be done later.
MAX_VERIFICATION_KEYS = 2

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX = re.compile(r"^[0-9A-Fa-f]+$")
#: A consumer name, as the outputs schema spells it. The same pattern, here,
#: because a key state validated by this module and a document validated by the
#: schema must agree about what a consumer may be called.
_CONSUMER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

__all__ = [
    "ALGORITHM",
    "MAX_VERIFICATION_KEYS",
    "PRIVATE_JWK_PARAMETERS",
    "PUBLIC_JWK_MEMBERS",
    "JwkError",
    "abandon_rotation",
    "base64url_decode",
    "base64url_encode",
    "build_jwks",
    "initial_key_state",
    "prepare_rotation",
    "promote_rotation",
    "public_jwk",
    "record_acknowledgement",
    "retire_rotation",
    "thumbprint",
    "unacknowledged",
    "validate_key_state",
]


class JwkError(ValueError):
    """A key, a key set or a rotation is not usable as stated."""


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def base64url_encode(raw: bytes) -> str:
    """Unpadded base64url, which is the only spelling JOSE accepts.

    Padding is stripped rather than left optional. A `kid` that compares unequal
    to itself across two encoders is a rotation that silently never completes:
    the new key is published, the old one is never recognised as the old one, and
    the verification set grows instead of turning over.
    """
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    """The inverse, restoring the padding the encoder removed."""
    if not _BASE64URL.match(value):
        raise JwkError(f"not unpadded base64url: {value!r}")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _integer_to_base64url(value: int) -> str:
    """A JOSE `n` or `e`: the big-endian minimal-length unsigned encoding.

    Minimal length matters and is easy to get wrong. A leading zero byte changes
    the base64url string without changing the number, so two encoders that
    disagree about padding produce two thumbprints for one key -- and the
    thumbprint is the identifier.
    """
    if value <= 0:
        raise JwkError(f"a JWK integer parameter must be positive, got {value}")
    return base64url_encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))


# ---------------------------------------------------------------------------
# The public key
# ---------------------------------------------------------------------------


def public_jwk(*, modulus_hex: str, exponent: int) -> dict[str, str]:
    """An RSA public JWK from what `openssl` prints about a key.

    `openssl rsa -noout -modulus` emits `Modulus=` followed by uppercase hex, and
    `-text` names the exponent in decimal. Both are read by the caller and passed
    here, so this module never runs a subprocess and never touches a key file.

    The `kid` is computed, not accepted. That is the whole of RFC 7638's value:
    the identifier is a function of the key, so a rotation cannot publish a new
    key under the old key's name, and two projects cannot accidentally share one.
    """
    cleaned = modulus_hex.strip().removeprefix("Modulus=").strip()
    if not _HEX.match(cleaned):
        raise JwkError(
            f"not a hexadecimal modulus: {modulus_hex!r}. `openssl rsa -noout -modulus` "
            "prints `Modulus=` and uppercase hex; anything else means the key was not read"
        )
    modulus = int(cleaned, 16)
    if modulus.bit_length() < 2048:
        raise JwkError(
            f"the modulus is {modulus.bit_length()} bits, below 2048. A key this short is "
            "not refused because a verifier would reject it -- most will not -- but "
            "because nothing should be signing with it"
        )
    if exponent < 3 or exponent % 2 == 0:
        raise JwkError(f"not a usable RSA public exponent: {exponent}")

    jwk = {
        "kty": "RSA",
        "n": _integer_to_base64url(modulus),
        "e": _integer_to_base64url(exponent),
        "alg": ALGORITHM,
        "use": "sig",
    }
    return {**jwk, "kid": thumbprint(jwk)}


def thumbprint(jwk: dict[str, Any]) -> str:
    """The RFC 7638 thumbprint: base64url SHA-256 of the canonical member set.

    Canonical means exactly three members for an RSA key -- `e`, `kty`, `n` --
    in lexicographic order, with no whitespace. Everything else in the JWK,
    including `alg`, `use` and any `kid` already present, is excluded by the
    specification. Including one would make the identifier depend on metadata
    rather than on the key, which is the property being bought.
    """
    missing = {"kty", "n", "e"} - set(jwk)
    if missing:
        raise JwkError(f"cannot compute a thumbprint without {sorted(missing)}")
    if jwk["kty"] != "RSA":
        raise JwkError(f"only RSA keys are handled here, got {jwk['kty']!r}")

    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64url_encode(sha256(canonical.encode("utf-8")).digest())


def assert_public(jwk: dict[str, Any]) -> None:
    """Refuse a JWK carrying private material (ADR 0051).

    This is the check that stops a private key being published to a verifier by
    a mistake in a derivation nobody reads. It refuses by parameter name against
    the complete RFC 7518 set rather than by checking for the members a public
    key has, because the failure to catch is an *extra* member, and a check
    written the other way round passes on a superset.
    """
    present = [parameter for parameter in PRIVATE_JWK_PARAMETERS if parameter in jwk]
    if present:
        raise JwkError(
            f"this JWK carries the private parameters {present}. It is a signing key, and "
            "the set PostgREST receives is verification-only"
        )
    unexpected = set(jwk) - PUBLIC_JWK_MEMBERS
    if unexpected:
        raise JwkError(
            f"unexpected JWK members {sorted(unexpected)}. The published set carries "
            f"exactly {sorted(PUBLIC_JWK_MEMBERS)}; anything else is a member nobody "
            "decided to publish"
        )


def build_jwks(keys: list[dict[str, Any]]) -> dict[str, Any]:
    """The verification-only key set PostgREST is given.

    Every rule is applied to every key, and the order of the list is preserved:
    the active key is first by convention, and a set whose order changed between
    two renders would make a byte comparison of the rendered file meaningless.
    """
    if not keys:
        raise JwkError("a key set with no keys verifies nothing")
    if len(keys) > MAX_VERIFICATION_KEYS:
        raise JwkError(
            f"{len(keys)} verification keys, above the ceiling of {MAX_VERIFICATION_KEYS}. "
            "An unbounded set is a set nobody retires from"
        )

    seen: set[str] = set()
    for jwk in keys:
        assert_public(jwk)
        if jwk.get("alg") != ALGORITHM:
            raise JwkError(
                f"key {jwk.get('kid')!r} declares alg {jwk.get('alg')!r}; this issuer is "
                f"{ALGORITHM} and a verifier that accepts two algorithms accepts the "
                "weaker one"
            )
        computed = thumbprint(jwk)
        if jwk.get("kid") != computed:
            raise JwkError(
                f"kid {jwk.get('kid')!r} is not this key's RFC 7638 thumbprint "
                f"({computed}). A kid chosen beside the key rather than derived from it "
                "can name a key that is not present"
            )
        if computed in seen:
            raise JwkError(f"two keys share the kid {computed}; they are the same key")
        seen.add(computed)

    return {"keys": [dict(jwk) for jwk in keys]}


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


def initial_key_state(*, jwk: dict[str, Any], temporary: bool = True) -> dict[str, Any]:
    """The `jwt` block's key members for a project with one key and no rotation.

    `verifier_acknowledgements` is **null** rather than `{}`, and the difference
    is a real one the schema also draws: an empty object says every verifier was
    asked and none has answered, and null says nothing has been asked. Before the
    first rotation the second is true.
    """
    assert_public(jwk)
    return {
        "algorithm": ALGORITHM,
        "active_kid": jwk["kid"],
        "verification_kids": [jwk["kid"]],
        "temporary": temporary,
        "retire_after": None,
        "verifier_acknowledgements": None,
    }


def prepare_rotation(state: dict[str, Any], *, incoming: dict[str, Any]) -> dict[str, Any]:
    """Phase one: publish both keys, and change nothing about what signs.

    **The active key does not move here**, and that separation is the whole of
    ADR 0088. `begin_rotation`, which this replaces, published two keys *and*
    switched signing in one step -- which cannot be made safe, because the moment
    the active key moves is the moment every verifier has to already hold the new
    one, and there was no step at which anything could have checked.

    After this, every token in existence is still signed by a key every verifier
    already had, and the new key verifies nowhere yet. Nothing has been risked.
    The next thing that happens is that the verifiers are recreated and each
    records what it loaded (`record_acknowledgement`), because a running
    PostgREST does not re-read its key set -- measured, a rewritten file left a
    running verifier refusing the new key while still accepting the old one.

    A rotation cannot begin while one is in flight. Two overlapping rotations
    would need three verification keys, and the third is the one that never gets
    removed.
    """
    validate_key_state(state)
    assert_public(incoming)

    if len(state["verification_kids"]) > 1:
        raise JwkError(
            f"a rotation is already in flight: {state['verification_kids']} are published. "
            "Beginning another would need a third verification key, and a third key is one "
            "nobody retires"
        )
    if incoming["kid"] == state["active_kid"]:
        raise JwkError(
            "the incoming key is the active key. Preparing a rotation to the same material "
            "publishes a second copy of one key, which is a rotation nobody performed"
        )

    return {
        **state,
        # Unchanged, and this is the line that distinguishes prepare from
        # promote. A reader comparing this state against the previous one sees
        # exactly one difference: a key was added to the verification set.
        "active_kid": state["active_kid"],
        # The ACTIVE key first. `build_jwks` preserves order, and the key that
        # signs leading the set is what makes a reader's first guess the right
        # one -- during a prepare that is still the old key.
        "verification_kids": [state["active_kid"], incoming["kid"]],
        "retire_after": None,
        # Cleared: an acknowledgement is of a specific published set, and the
        # set has just changed. Carrying the previous round's digests forward
        # would let a promotion be authorised by verifiers that acknowledged a
        # key set that no longer exists -- which is the assumption about
        # propagation this whole mechanism exists to replace.
        "verifier_acknowledgements": {},
    }


def record_acknowledgement(
    state: dict[str, Any], *, consumer: str, jwks_sha256: str
) -> dict[str, Any]:
    """Phase two: one verifier has loaded a key set, and this is which one.

    The digest is of what the consumer's **running process** holds, read from
    the container rather than from the host file it was supposed to have read.
    That distinction is the one that matters and it is not theoretical: the
    deploy writes the key set by atomic replace, which creates a new inode, and
    a file bind mount binds the inode -- so a verifier can be looking at a file
    that no longer exists while the host holds the correct one. Measured, with
    an in-place rewrite as the control.

    Nothing here decides whether the digest is the right one. `promote_rotation`
    does, against the set actually published, so that a consumer cannot
    acknowledge its way past a rotation by reporting a digest nobody asked for.
    """
    validate_key_state(state)
    if not consumer or not _CONSUMER.match(consumer):
        raise JwkError(f"not a usable consumer name: {consumer!r}")
    if not _SHA256.match(jwks_sha256):
        raise JwkError(f"not a sha256 digest: {jwks_sha256!r}")

    acknowledgements = dict(state.get("verifier_acknowledgements") or {})
    acknowledgements[consumer] = jwks_sha256
    return {**state, "verifier_acknowledgements": acknowledgements}


def unacknowledged(state: dict[str, Any], *, consumers: list[str], jwks_sha256: str) -> list[str]:
    """The consumers that have not recorded this exact digest.

    Returned rather than counted, because the message an operator needs is
    *which* verifier is behind. An empty list is what `promote_rotation`
    requires; anything else names what to recreate.
    """
    acknowledgements = state.get("verifier_acknowledgements") or {}
    return sorted(name for name in consumers if acknowledgements.get(name) != jwks_sha256)


def promote_rotation(
    state: dict[str, Any],
    *,
    incoming_kid: str,
    consumers: list[str],
    jwks_sha256: str,
    now: datetime,
    max_token_ttl_seconds: int,
    clock_skew_seconds: int,
) -> dict[str, Any]:
    """Phase three: sign with the new key, and only once everyone can verify it.

    **This is the irreversible step**, and the refusal above it is the thing
    that makes it safe. Promoting while any verifier still holds the previous
    key set means signing tokens that verifier will refuse, and the failure
    arrives at whoever holds one -- as an authentication error with no cause
    visible from where it is seen.

    The check is against a *recorded* digest per consumer, not against elapsed
    time and not against the host's copy of the file. A consumer that has not
    been recreated cannot have acknowledged, which is exactly the state that
    must block this.

    The deadline is `now + max_token_ttl + clock_skew`: the moment after which no
    token signed by the retiring key can still be inside its own lifetime. It is
    computed here rather than at retirement, because at retirement the moment the
    switch happened is exactly what nobody remembers.
    """
    validate_key_state(state)

    if incoming_kid not in state["verification_kids"]:
        raise JwkError(
            f"{incoming_kid} is not published: the set is {state['verification_kids']}. "
            "Promote what prepare published, or prepare first"
        )
    if incoming_kid == state["active_kid"]:
        raise JwkError(f"{incoming_kid} is already the active key; there is nothing to promote")
    if not consumers:
        raise JwkError(
            "no verifiers were named. Promotion is blocked on every verifier having "
            "acknowledged, and an empty list makes that condition vacuously true -- which "
            "is the shape of a check that cannot fail"
        )
    if not _SHA256.match(jwks_sha256):
        raise JwkError(f"not a sha256 digest: {jwks_sha256!r}")

    behind = unacknowledged(state, consumers=consumers, jwks_sha256=jwks_sha256)
    if behind:
        raise JwkError(
            f"{behind} have not acknowledged the prepared key set ({jwks_sha256[:16]}…). "
            "Promoting now would sign tokens they refuse. A verifier acknowledges by being "
            "RECREATED against the published set -- a running one never re-reads it"
        )
    if max_token_ttl_seconds < 1 or clock_skew_seconds < 0:
        raise JwkError("the overlap window must be a positive token lifetime plus a skew")

    retiring = [kid for kid in state["verification_kids"] if kid != incoming_kid]
    deadline = now.astimezone(UTC) + timedelta(seconds=max_token_ttl_seconds + clock_skew_seconds)
    return {
        **state,
        "active_kid": incoming_kid,
        # The newly active key leads, and the retiring one follows it.
        "verification_kids": [incoming_kid, *retiring],
        "retire_after": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def retire_rotation(state: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Phase four: publish only the active key, and not before the deadline.

    Refusing early is the half that matters. Retiring before the window closes
    invalidates tokens that are still inside their own lifetime, and the failure
    arrives at whoever holds one with no cause visible from where it is seen.

    The acknowledgements are cleared: they described the two-key set that has
    just stopped being published, and a digest kept past the set it describes is
    a record that would authorise the next promotion for free.
    """
    validate_key_state(state)
    if state["retire_after"] is None:
        raise JwkError("no rotation is in flight; there is nothing to retire")

    deadline = datetime.strptime(state["retire_after"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if now.astimezone(UTC) < deadline:
        raise JwkError(
            f"the overlap window closes at {state['retire_after']} and it is "
            f"{now.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}. Removing the retiring "
            "key now would refuse tokens that are still inside their own lifetime"
        )

    return {
        **state,
        "verification_kids": [state["active_kid"]],
        "retire_after": None,
        "verifier_acknowledgements": {},
    }


def abandon_rotation(state: dict[str, Any]) -> dict[str, Any]:
    """Undo a prepare that has not been promoted.

    The only rollback this design has, and it is available for exactly one
    phase. Before promotion nothing is signing with the incoming key, so
    republishing the active key alone costs nothing and invalidates no token.
    After promotion there is no way back -- the retired key's private material
    is gone -- and the recovery is to complete forward.
    """
    validate_key_state(state)
    if state["retire_after"] is not None:
        raise JwkError(
            f"this rotation was promoted and is due to retire after {state['retire_after']}. "
            "There is no path back to the previous signing key; complete it forward"
        )
    if len(state["verification_kids"]) == 1:
        raise JwkError("no rotation is prepared; there is nothing to abandon")

    return {
        **state,
        "verification_kids": [state["active_kid"]],
        "verifier_acknowledgements": {},
    }


def validate_key_state(state: dict[str, Any]) -> dict[str, Any]:
    """The invariants of the `jwt` block's key members, wherever it came from.

    Applied on the way in as well as on the way out, so a state read from a
    deployed document written by an older release is checked before it is used to
    decide anything.
    """
    required = {
        "algorithm",
        "active_kid",
        "verification_kids",
        "temporary",
        "retire_after",
        # Version 9, and required here since ADR 0088 made it the thing
        # promotion is blocked on. A state without it is one where the gate
        # cannot be evaluated, which must be an error rather than a default.
        "verifier_acknowledgements",
    }
    missing = required - set(state)
    if missing:
        raise JwkError(f"the key state is missing {sorted(missing)}")

    if state["algorithm"] != ALGORITHM:
        raise JwkError(f"algorithm {state['algorithm']!r} is not {ALGORITHM}")

    kids = state["verification_kids"]
    if not isinstance(kids, list) or not kids:
        raise JwkError("verification_kids must be a non-empty list")
    if len(kids) > MAX_VERIFICATION_KEYS:
        raise JwkError(f"{len(kids)} verification kids, above {MAX_VERIFICATION_KEYS}")
    if len(set(kids)) != len(kids):
        raise JwkError(f"verification_kids repeats a key: {kids}")
    if state["active_kid"] not in kids:
        raise JwkError(
            f"active_kid {state['active_kid']!r} is not in verification_kids {kids}. Every "
            "token this issuer signs would be refused by every verifier reading this"
        )

    # A deadline needs a second key to be about. One key with a deadline is a
    # rotation whose retirement would remove nothing.
    #
    # The converse is NOT an error any more, and that is ADR 0088's split: two
    # keys with no deadline is a *prepared* rotation, published so that every
    # verifier can be recreated against it before anything starts signing with
    # the new one. `begin_rotation` had no such state, which is why it could not
    # be made safe -- and why the invariant here used to say a deadline and a
    # second key were the same fact.
    if state["retire_after"] is not None and len(kids) == 1:
        raise JwkError(
            f"retire_after is {state['retire_after']!r} beside one verification key. "
            "A deadline is the moment a retiring key stops being needed, and there is "
            "no retiring key here"
        )

    acknowledgements = state["verifier_acknowledgements"]
    if acknowledgements is not None:
        if not isinstance(acknowledgements, dict):
            raise JwkError(
                f"verifier_acknowledgements is {type(acknowledgements).__name__}; it is a "
                "map of consumer name to the digest that consumer has loaded, or null"
            )
        for consumer, digest in acknowledgements.items():
            if not _CONSUMER.match(str(consumer)):
                raise JwkError(f"not a usable consumer name: {consumer!r}")
            if not _SHA256.match(str(digest)):
                raise JwkError(f"{consumer} acknowledges {digest!r}, which is not a sha256")
    return state
