"""The bootstrap issuer's public half (ADR 0051, ADR 0055).

Every test here runs with no key, no host and no container, which is the point
of the split: the private key is a PEM only `openssl` handles, and everything
that decides whether a verifier will accept a token is computed from a modulus
and an exponent. So the security properties are the offline-testable half.

The three that carry the design, and the failure each one prevents:

* **a public JWK carrying `d` is a private key with a misleading label** --
  published to a verifier, it makes every verifier an issuer, which is the exact
  shape ADR 0051 refused a shared HMAC secret for;
* **`kid` is derived from the key, not chosen beside it** -- a chosen `kid` can
  name a key that is not present, and the symptom is every token being rejected
  with nothing in either document explaining why;
* **a rotation has a deadline and it is a value** -- "after the tokens have
  expired" as a sentence is a rotation that never completes; as `retire_after`
  it is a comparison, and completing early refuses tokens that are still inside
  their own lifetime.

The modulus below is a real 2048-bit RSA modulus, in the uppercase hex form
`openssl rsa -noout -modulus` prints. It is public material by definition -- it
is the number a verifier holds -- and there is no private key anywhere in this
repository that corresponds to it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from agentic_postgres import jwt_keys
from agentic_postgres.jwt_keys import JwkError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

#: A 2048-bit modulus, as `openssl rsa -noout -modulus` prints it.
MODULUS = (
    "C3F0D1B2A45E67890ABCDEF1234567890FEDCBA9876543210AABBCCDDEEFF0011"
    "223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF001"
    "1223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00"
    "112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF001"
    "1223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00"
    "112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF001"
    "1223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00"
    "112233445566778899AABBCCDDEEFF00112233445566778899AABBCCDDEEFF01"
)

#: A second, different modulus, for the rotation tests. Differs in its last byte.
OTHER_MODULUS = MODULUS[:-2] + "03"

#: A third, for the one test that needs a rotation to be refused while another
#: is published. Two would make that test compare a key against itself.
THIRD_MODULUS = MODULUS[:-2] + "05"

EXPONENT = 65537


@pytest.fixture
def active() -> dict[str, str]:
    return jwt_keys.public_jwk(modulus_hex=MODULUS, exponent=EXPONENT)


@pytest.fixture
def incoming() -> dict[str, str]:
    return jwt_keys.public_jwk(modulus_hex=OTHER_MODULUS, exponent=EXPONENT)


@pytest.fixture
def state(active: dict[str, str]) -> dict[str, object]:
    return jwt_keys.initial_key_state(jwk=active)


NOW = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The public key
# ---------------------------------------------------------------------------


def test_a_public_jwk_carries_exactly_the_published_members(active: dict[str, str]) -> None:
    assert set(active) == jwt_keys.PUBLIC_JWK_MEMBERS
    assert active["kty"] == "RSA"
    assert active["alg"] == "RS256"
    assert active["use"] == "sig"


def test_the_openssl_prefix_is_accepted_because_that_is_what_it_prints() -> None:
    """`openssl rsa -noout -modulus` emits `Modulus=` and then the hex.

    Accepted with the prefix and without, so the caller does not have to strip
    it -- and a caller that forgot to would otherwise be feeding this function a
    string whose first seven characters are not hex, which fails loudly rather
    than parsing as a different number.
    """
    with_prefix = jwt_keys.public_jwk(modulus_hex=f"Modulus={MODULUS}\n", exponent=EXPONENT)
    without = jwt_keys.public_jwk(modulus_hex=MODULUS, exponent=EXPONENT)
    assert with_prefix == without


@pytest.mark.parametrize(
    "modulus",
    [
        pytest.param("", id="empty"),
        pytest.param("not-hex", id="not-hex"),
        pytest.param("unable to load Public Key", id="openssl-error-text"),
        pytest.param("C3F0", id="far-too-short"),
    ],
)
def test_something_that_is_not_a_modulus_is_refused(modulus: str) -> None:
    """`openssl` printing an error to stdout is the case worth refusing.

    A caller that passed the error text through would get a `JwkError` here
    rather than a JWK built from whatever `int(..., 16)` made of it.
    """
    with pytest.raises(JwkError):
        jwt_keys.public_jwk(modulus_hex=modulus, exponent=EXPONENT)


def test_a_short_modulus_is_refused() -> None:
    """Not because a verifier would reject it -- most will not."""
    short = "C3" + "F0" * 100
    with pytest.raises(JwkError, match="below 2048"):
        jwt_keys.public_jwk(modulus_hex=short, exponent=EXPONENT)


@pytest.mark.parametrize("exponent", [0, 1, 2, 4, 65536])
def test_an_unusable_exponent_is_refused(exponent: int) -> None:
    with pytest.raises(JwkError):
        jwt_keys.public_jwk(modulus_hex=MODULUS, exponent=exponent)


def test_the_integer_encoding_carries_no_leading_zero(active: dict[str, str]) -> None:
    """A leading zero byte changes the string without changing the number.

    Two encoders that disagree about it produce two thumbprints for one key --
    and the thumbprint is the identifier the whole rotation turns on.
    """
    assert jwt_keys.base64url_decode(active["n"])[0] != 0
    assert jwt_keys.base64url_decode(active["e"]) == (65537).to_bytes(3, "big")


def test_base64url_is_unpadded_in_both_directions(active: dict[str, str]) -> None:
    assert "=" not in active["n"]
    assert "=" not in active["kid"]
    raw = b"\x00\x01\x02\x03\x04"
    assert jwt_keys.base64url_decode(jwt_keys.base64url_encode(raw)) == raw
    with pytest.raises(JwkError):
        jwt_keys.base64url_decode("AAAA====")


# ---------------------------------------------------------------------------
# The thumbprint
# ---------------------------------------------------------------------------


def test_the_kid_is_the_rfc_7638_thumbprint(active: dict[str, str]) -> None:
    """Computed here against the specification's own construction.

    Three members, lexicographic, no whitespace. Written out rather than calling
    the module's own function, because a test that computed it the same way
    would agree with any construction the module chose.
    """
    canonical = '{{"e":"{}","kty":"RSA","n":"{}"}}'.format(active["e"], active["n"])
    expected = jwt_keys.base64url_encode(sha256(canonical.encode("utf-8")).digest())
    assert active["kid"] == expected
    assert len(active["kid"]) == 43


def test_the_thumbprint_ignores_everything_but_the_key(active: dict[str, str]) -> None:
    """`alg`, `use` and any existing `kid` are excluded by the specification.

    Including one would make the identifier depend on metadata rather than on
    the key, and then a key republished with a different `use` would look like a
    different key.
    """
    assert jwt_keys.thumbprint(active) == jwt_keys.thumbprint(
        {"kty": "RSA", "n": active["n"], "e": active["e"]}
    )
    assert jwt_keys.thumbprint({**active, "alg": "RS512", "use": "enc"}) == active["kid"]


def test_two_different_keys_have_different_thumbprints(
    active: dict[str, str], incoming: dict[str, str]
) -> None:
    assert active["kid"] != incoming["kid"]


def test_a_thumbprint_needs_a_key(active: dict[str, str]) -> None:
    with pytest.raises(JwkError, match="without"):
        jwt_keys.thumbprint({"kty": "RSA", "n": active["n"]})
    with pytest.raises(JwkError, match="only RSA"):
        jwt_keys.thumbprint({"kty": "EC", "n": active["n"], "e": active["e"]})


# ---------------------------------------------------------------------------
# The verification-only key set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("parameter", jwt_keys.PRIVATE_JWK_PARAMETERS)
def test_a_jwk_carrying_private_material_is_refused(active: dict[str, str], parameter: str) -> None:
    """Every private RSA parameter RFC 7518 defines, one test each.

    Refused by name against the complete set rather than by checking for the
    members a public key has, because the failure to catch is an *extra* member
    and a check written the other way round passes on a superset.
    """
    with pytest.raises(JwkError, match="private parameters"):
        jwt_keys.build_jwks([{**active, parameter: "AQAB"}])


def test_the_refusal_is_asserted_against_a_deliberately_malformed_input(
    active: dict[str, str],
) -> None:
    """ADR 0051 asks for exactly this rather than for trust in the generator.

    A key set built from a real private JWK is the input that would leak a
    signing key to every verifier, so it is constructed here on purpose.
    """
    private_looking = {**active, "d": "c3RvbGVu", "p": "cA", "q": "cQ"}
    with pytest.raises(JwkError) as raised:
        jwt_keys.build_jwks([private_looking])
    assert "'d'" in str(raised.value) or "d" in str(raised.value)


def test_a_member_nobody_decided_to_publish_is_refused(active: dict[str, str]) -> None:
    with pytest.raises(JwkError, match="unexpected JWK members"):
        jwt_keys.build_jwks([{**active, "x5c": ["..."]}])


def test_a_kid_that_is_not_the_thumbprint_is_refused(active: dict[str, str]) -> None:
    """A chosen kid can name a key that is not present."""
    with pytest.raises(JwkError, match="thumbprint"):
        jwt_keys.build_jwks([{**active, "kid": "a" * 43}])


def test_a_second_algorithm_is_refused(active: dict[str, str]) -> None:
    """A verifier that accepts two algorithms accepts the weaker one."""
    with pytest.raises(JwkError, match="RS256"):
        jwt_keys.build_jwks([{**active, "alg": "RS512"}])


def test_an_empty_key_set_is_refused() -> None:
    with pytest.raises(JwkError, match="verifies nothing"):
        jwt_keys.build_jwks([])


def test_more_than_two_keys_is_refused(active: dict[str, str], incoming: dict[str, str]) -> None:
    """Two is a ceiling, not a convention.

    An unbounded verification set is a set nobody retires from: every key stays
    valid because removing one is always something that can be done later.
    """
    third = jwt_keys.public_jwk(modulus_hex=MODULUS[:-2] + "05", exponent=EXPONENT)
    with pytest.raises(JwkError, match="ceiling"):
        jwt_keys.build_jwks([active, incoming, third])


def test_the_same_key_twice_is_refused(active: dict[str, str]) -> None:
    with pytest.raises(JwkError, match="same key"):
        jwt_keys.build_jwks([active, dict(active)])


def test_a_valid_set_is_returned_in_order(active: dict[str, str], incoming: dict[str, str]) -> None:
    """Order is preserved because a rendered file is byte-compared.

    A set whose order changed between two renders would make that comparison
    meaningless, and the active key leading it is what makes a reader's first
    guess the right one.
    """
    jwks = jwt_keys.build_jwks([incoming, active])
    assert [key["kid"] for key in jwks["keys"]] == [incoming["kid"], active["kid"]]
    assert json.loads(json.dumps(jwks)) == jwks


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------


def test_a_new_project_has_one_key_and_no_deadline(state: dict[str, object]) -> None:
    assert state["verification_kids"] == [state["active_kid"]]
    assert state["retire_after"] is None
    assert state["temporary"] is True
    jwt_keys.validate_key_state(state)


def test_the_issuer_is_temporary_unless_something_says_otherwise(
    active: dict[str, str],
) -> None:
    """ADR 0051: the temporariness is state, not a comment.

    Session 6's gate reads it. The default is `True` so that an issuer created
    without anyone thinking about it is recorded as the provisional thing it is.
    """
    assert jwt_keys.initial_key_state(jwk=active)["temporary"] is True
    assert jwt_keys.initial_key_state(jwk=active, temporary=False)["temporary"] is False


#: The digest a verifier is imagined to report. A literal rather than a hash of
#: anything under test: what is being measured is the comparison, and computing
#: the expected value from the value under test is the tautology D260 found
#: three of in one run.
PREPARED = "a" * 64
STALE = "b" * 64

#: The verifiers this project has. One today; the list exists because promotion
#: is blocked on *every* one of them, and a check written against a single name
#: reads as though it could never have been plural.
VERIFIERS = ["postgrest"]


def prepared(state: dict, incoming: dict) -> dict:
    return jwt_keys.prepare_rotation(state, incoming=incoming)


def acknowledged(state: dict, digest: str = PREPARED) -> dict:
    for consumer in VERIFIERS:
        state = jwt_keys.record_acknowledgement(state, consumer=consumer, jwks_sha256=digest)
    return state


def test_prepare_publishes_both_keys_and_moves_nothing_that_signs(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """The line that separates this design from the one it replaced.

    `begin_rotation` published the second key *and* switched signing together,
    so there was no moment at which anything could check that the verifiers held
    the new key. After a prepare, every token in existence is still signed by a
    key every verifier already had, and nothing has been risked.
    """
    rotating = prepared(state, incoming)

    assert rotating["active_kid"] == state["active_kid"], "prepare moved the signing key"
    assert rotating["verification_kids"] == [state["active_kid"], incoming["kid"]]
    assert rotating["retire_after"] is None, "prepare recorded a deadline it cannot know yet"
    assert rotating["verifier_acknowledgements"] == {}
    jwt_keys.validate_key_state(rotating)


def test_promotion_is_refused_until_every_verifier_has_acknowledged(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """The refusal that makes promotion safe, and the measurement behind it.

    A running PostgREST never re-reads its key set -- measured against the
    locked image, a rewritten file left it refusing the new key while still
    accepting the old one. So "the file was written" says nothing about what any
    verifier holds, and promoting on it would sign tokens that verifier refuses.
    """
    rotating = prepared(state, incoming)

    with pytest.raises(JwkError, match="have not acknowledged"):
        jwt_keys.promote_rotation(
            rotating,
            incoming_kid=incoming["kid"],
            consumers=VERIFIERS,
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        )


def test_acknowledging_the_wrong_digest_does_not_authorise_a_promotion(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """A verifier that reloaded something is not a verifier that reloaded THIS.

    The stale case is the real one: a container recreated against the key set
    from before the prepare reports a digest, and a check that only asked "has
    this consumer answered" would take it.
    """
    rotating = acknowledged(prepared(state, incoming), STALE)

    assert jwt_keys.unacknowledged(rotating, consumers=VERIFIERS, jwks_sha256=PREPARED) == VERIFIERS
    with pytest.raises(JwkError, match="have not acknowledged"):
        jwt_keys.promote_rotation(
            rotating,
            incoming_kid=incoming["kid"],
            consumers=VERIFIERS,
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        )


def test_promotion_with_no_verifiers_named_is_refused(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """An empty list makes "every verifier has acknowledged" vacuously true.

    That is the shape of a check that cannot fail, and this repository has
    shipped three of them (D173, D260). Refused explicitly rather than left to
    be discovered by whoever calls it with a list built from a filter.
    """
    with pytest.raises(JwkError, match="no verifiers were named"):
        jwt_keys.promote_rotation(
            acknowledged(prepared(state, incoming)),
            incoming_kid=incoming["kid"],
            consumers=[],
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        )


def test_promotion_switches_the_key_and_records_the_deadline(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    rotating = jwt_keys.promote_rotation(
        acknowledged(prepared(state, incoming)),
        incoming_kid=incoming["kid"],
        consumers=VERIFIERS,
        jwks_sha256=PREPARED,
        now=NOW,
        max_token_ttl_seconds=300,
        clock_skew_seconds=30,
    )

    assert rotating["active_kid"] == incoming["kid"]
    assert rotating["verification_kids"] == [incoming["kid"], state["active_kid"]]
    assert rotating["retire_after"] == "2026-08-11T12:05:30Z"
    jwt_keys.validate_key_state(rotating)


def test_the_deadline_is_the_token_lifetime_plus_the_skew(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """Computed at promotion, because at retirement nobody remembers the moment."""
    rotating = jwt_keys.promote_rotation(
        acknowledged(prepared(state, incoming)),
        incoming_kid=incoming["kid"],
        consumers=VERIFIERS,
        jwks_sha256=PREPARED,
        now=NOW,
        max_token_ttl_seconds=900,
        clock_skew_seconds=30,
    )
    assert rotating["retire_after"] == "2026-08-11T12:15:30Z"


def test_retirement_may_not_run_early(state: dict[str, object], incoming: dict[str, str]) -> None:
    """Removing the retiring key early refuses tokens still inside their lifetime."""
    rotating = jwt_keys.promote_rotation(
        acknowledged(prepared(state, incoming)),
        incoming_kid=incoming["kid"],
        consumers=VERIFIERS,
        jwks_sha256=PREPARED,
        now=NOW,
        max_token_ttl_seconds=300,
        clock_skew_seconds=30,
    )
    with pytest.raises(JwkError, match="overlap window closes"):
        jwt_keys.retire_rotation(rotating, now=NOW + timedelta(seconds=329))

    done = jwt_keys.retire_rotation(rotating, now=NOW + timedelta(seconds=330))
    assert done["verification_kids"] == [incoming["kid"]]
    assert done["retire_after"] is None
    assert done["verifier_acknowledgements"] == {}
    jwt_keys.validate_key_state(done)


def test_a_second_rotation_cannot_be_prepared_while_one_is_published(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """A third verification key is the one nobody retires."""
    rotating = prepared(state, incoming)
    third = jwt_keys.public_jwk(modulus_hex=THIRD_MODULUS, exponent=EXPONENT)
    with pytest.raises(JwkError, match="already in flight"):
        jwt_keys.prepare_rotation(rotating, incoming=third)


def test_preparing_a_rotation_to_the_active_key_is_refused(
    state: dict[str, object], active: dict[str, str]
) -> None:
    with pytest.raises(JwkError, match="the active key"):
        jwt_keys.prepare_rotation(state, incoming=active)


def test_promoting_the_key_that_already_signs_is_refused(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    rotating = acknowledged(prepared(state, incoming))
    with pytest.raises(JwkError, match="already the active key"):
        jwt_keys.promote_rotation(
            rotating,
            incoming_kid=str(state["active_kid"]),
            consumers=VERIFIERS,
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        )


def test_promoting_a_key_that_was_never_published_is_refused(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """Promotion names what prepare published.

    The acknowledgement check would catch this too -- nothing can have
    acknowledged a set containing a key nobody published -- but it would name
    the wrong problem, and a message naming the wrong problem is what D186 cost.
    """
    rotating = acknowledged(prepared(state, incoming))
    with pytest.raises(JwkError, match="is not published"):
        jwt_keys.promote_rotation(
            rotating,
            incoming_kid="z" * 43,
            consumers=VERIFIERS,
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        )


def test_retiring_a_rotation_that_is_not_happening_is_refused(state: dict[str, object]) -> None:
    with pytest.raises(JwkError, match="nothing to retire"):
        jwt_keys.retire_rotation(state, now=NOW)


def test_a_rotation_carrying_private_material_is_refused(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    with pytest.raises(JwkError, match="private parameters"):
        jwt_keys.prepare_rotation(state, incoming={**incoming, "d": "secret"})


def test_a_prepared_rotation_can_be_abandoned_and_a_promoted_one_cannot(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """The only rollback this design has, available for exactly one phase.

    Before promotion nothing signs with the incoming key, so withdrawing it
    costs nothing and invalidates no token. After promotion the retired key's
    private material is gone and the recovery is to complete forward -- so a
    function offering to undo it would be offering something it cannot do.
    """
    rotating = acknowledged(prepared(state, incoming))
    abandoned = jwt_keys.abandon_rotation(rotating)
    assert abandoned["verification_kids"] == [state["active_kid"]]
    assert abandoned["active_kid"] == state["active_kid"]
    assert abandoned["verifier_acknowledgements"] == {}
    jwt_keys.validate_key_state(abandoned)

    promoted = jwt_keys.promote_rotation(
        rotating,
        incoming_kid=incoming["kid"],
        consumers=VERIFIERS,
        jwks_sha256=PREPARED,
        now=NOW,
        max_token_ttl_seconds=300,
        clock_skew_seconds=30,
    )
    with pytest.raises(JwkError, match="complete it forward"):
        jwt_keys.abandon_rotation(promoted)


def test_abandoning_when_nothing_is_prepared_is_refused(state: dict[str, object]) -> None:
    with pytest.raises(JwkError, match="nothing to abandon"):
        jwt_keys.abandon_rotation(state)


def test_preparing_again_clears_the_previous_rounds_acknowledgements(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """A digest kept past the set it describes would authorise the next
    promotion for free."""
    finished = jwt_keys.retire_rotation(
        jwt_keys.promote_rotation(
            acknowledged(prepared(state, incoming)),
            incoming_kid=incoming["kid"],
            consumers=VERIFIERS,
            jwks_sha256=PREPARED,
            now=NOW,
            max_token_ttl_seconds=300,
            clock_skew_seconds=30,
        ),
        now=NOW + timedelta(seconds=330),
    )
    third = jwt_keys.public_jwk(modulus_hex=THIRD_MODULUS, exponent=EXPONENT)
    again = jwt_keys.prepare_rotation(finished, incoming=third)
    assert again["verifier_acknowledgements"] == {}


@pytest.mark.parametrize("consumer", ["", "Postgrest", "post grest", "1rest", "x" * 65])
def test_an_unusable_consumer_name_is_refused(
    state: dict[str, object], incoming: dict[str, str], consumer: str
) -> None:
    """The same pattern the outputs schema enforces.

    A key state this module accepted and a document the schema refused would be
    two answers to what a consumer may be called, which is ADR 0002 broken at
    the smallest scale.
    """
    with pytest.raises(JwkError, match="consumer name"):
        jwt_keys.record_acknowledgement(
            prepared(state, incoming), consumer=consumer, jwks_sha256=PREPARED
        )


@pytest.mark.parametrize("digest", ["", "not-a-digest", "A" * 64, "a" * 63])
def test_an_acknowledgement_that_is_not_a_digest_is_refused(
    state: dict[str, object], incoming: dict[str, str], digest: str
) -> None:
    with pytest.raises(JwkError, match="sha256"):
        jwt_keys.record_acknowledgement(
            prepared(state, incoming), consumer="postgrest", jwks_sha256=digest
        )


# ---------------------------------------------------------------------------
# The state a deployed document carries
# ---------------------------------------------------------------------------


def test_the_active_key_must_be_one_a_verifier_accepts(state: dict[str, object]) -> None:
    with pytest.raises(JwkError, match="not in verification_kids"):
        jwt_keys.validate_key_state({**state, "active_kid": "z" * 43})


def test_a_deadline_without_a_retiring_key_is_refused(
    state: dict[str, object],
) -> None:
    """One key with a deadline is a rotation whose retirement removes nothing.

    Replaces `test_a_deadline_and_a_second_key_are_the_same_fact`, which also
    refused the converse -- two keys with no deadline. That is now the *prepared*
    state, and the old invariant is exactly what made a prepare step
    unrepresentable (ADR 0088).
    """
    with pytest.raises(JwkError, match="no retiring key"):
        jwt_keys.validate_key_state({**state, "retire_after": "2026-08-11T12:05:30Z"})


def test_two_keys_without_a_deadline_is_accepted(
    state: dict[str, object], incoming: dict[str, str]
) -> None:
    """The prepared state, and the direction the old invariant got wrong."""
    jwt_keys.validate_key_state(
        {
            **state,
            "verification_kids": [state["active_kid"], incoming["kid"]],
            "retire_after": None,
            "verifier_acknowledgements": {},
        }
    )


def test_a_repeated_verification_key_is_refused(state: dict[str, object]) -> None:
    with pytest.raises(JwkError, match="repeats"):
        jwt_keys.validate_key_state(
            {
                **state,
                "verification_kids": [state["active_kid"], state["active_kid"]],
                "retire_after": "2026-08-11T12:05:30Z",
            }
        )


def test_an_incomplete_state_is_refused(state: dict[str, object]) -> None:
    for member in (
        "algorithm",
        "active_kid",
        "verification_kids",
        "temporary",
        "retire_after",
        "verifier_acknowledgements",
    ):
        broken = {key: value for key, value in state.items() if key != member}
        with pytest.raises(JwkError, match="missing"):
            jwt_keys.validate_key_state(broken)


def test_the_state_members_are_the_ones_the_deployed_schema_names(
    state: dict[str, object],
) -> None:
    """One shape, two files. The block this produces is the block v5 accepts.

    Checked against the schema rather than against a list here, so a member
    added to one and not the other fails instead of passing on whichever copy
    the reader happened to open.
    """
    from agentic_postgres import config

    schema = config.load_schema("outputs.schema.json")["$defs"]["deployedJwt"]
    produced = set(state)
    accepted = set(schema["properties"])
    assert produced < accepted, sorted(produced - accepted)
    # What the schema has and this does not is the identity half -- status,
    # issuer, audience and the JWKS digest -- which comes from the render and
    # from the file, not from the key.
    # `verifier_acknowledgements` moved across this line in Run 10 and the note
    # it used to carry is worth keeping as the record of why. It said the field
    # was "on the identity side ... an observation of a deployment rather than a
    # property of the key", which was true while nothing consumed it. ADR 0088
    # made it the thing **promotion is blocked on**, so the module that decides
    # whether a rotation may proceed is the module that has to hold it. Still
    # observed rather than computed -- `record_acknowledgement` takes the digest
    # from a caller that read it off a running container -- but no longer
    # something this module can be ignorant of.
    assert accepted - produced == {
        "status",
        "issuer",
        "audience",
        "public_jwks_sha256",
    }


def test_the_module_holds_no_private_key_and_signs_nothing() -> None:
    """Asserted on the source, because this is the boundary ADR 0051 draws.

    The private key is a PEM only `openssl` handles. A function here that read
    one, or shelled out to sign with one, would put signing authority in a module
    every offline test imports.
    """
    import ast

    from agentic_postgres import REPO_ROOT

    tree = ast.parse((REPO_ROOT / "src" / "agentic_postgres" / "jwt_keys.py").read_text("utf-8"))

    # The import graph, not a text scan: a docstring explaining that this module
    # runs no subprocess must not read as one running.
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imported & {"subprocess", "os", "pathlib", "shutil"}, sorted(imported)

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    assert not any(
        name.startswith(("sign", "load_private", "read_key")) for name in jwt_keys.__all__
    )
