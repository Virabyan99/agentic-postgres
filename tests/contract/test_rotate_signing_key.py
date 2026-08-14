"""The signing-key cutover's operator surface (ADR 0088).

`jwt_keys` holds the rules and `tests/contract/test_jwt_keys.py` measures them.
What is asserted here is the layer between those rules and a deployment: which
components count as verifiers, where an acknowledgement is read from, and that
the refusals reach an operator as refusals rather than as tracebacks.

**The property that carries this file** is that an acknowledgement is read from
the verifier's *running container* and never from the host's copy of the key
set. The two differ exactly when it matters: the deploy writes the key set by
atomic replace, which creates a new inode, and a file bind mount binds the
inode -- so the host can hold the correct set while the process reads one that
no longer exists. Measured in Run 10, with an in-place rewrite as the control.
A command that hashed the host file would report every verifier as current and
would have been the acknowledgement step agreeing with the issuer.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, jwt_keys, runtime_override

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

COMMAND = REPO_ROOT / "bin" / "rotate-signing-key.py"

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
OTHER = MODULUS[:-2] + "03"
PUBLISHED = "c" * 64


@pytest.fixture(scope="module")
def command() -> Any:
    """The module, imported. Every side effect is behind `main()`."""
    specification = importlib.util.spec_from_file_location("apg_rotate_signing_key", COMMAND)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def document(**jwt: object) -> dict:
    active = jwt_keys.public_jwk(modulus_hex=MODULUS, exponent=65537)
    block = {
        "status": "ready",
        "issuer": "https://probe.test/api/app/auth",
        "audience": "urn:agentic-postgres:probe:dev",
        "public_jwks_sha256": PUBLISHED,
        **jwt_keys.initial_key_state(jwk=active),
        **jwt,
    }
    return {
        "project": {"key": "probe-dev"},
        "deployed_through_session": 6,
        "jwt": block,
    }


def prepared_document() -> dict:
    active = jwt_keys.public_jwk(modulus_hex=MODULUS, exponent=65537)
    incoming = jwt_keys.public_jwk(modulus_hex=OTHER, exponent=65537)
    state = jwt_keys.prepare_rotation(jwt_keys.initial_key_state(jwk=active), incoming=incoming)
    return document(**state)


# ---------------------------------------------------------------------------
# Who counts as a verifier
# ---------------------------------------------------------------------------


def test_the_verifiers_are_the_services_that_verify_and_not_the_issuer(command: Any) -> None:
    """The auth service holds the private key. An acknowledgement from it would
    be the issuer agreeing with itself, which is the exact shape of a check that
    cannot fail."""
    assert runtime_override.REST_SERVICE in command.VERIFIERS
    assert runtime_override.AUTH_SERVICE not in command.VERIFIERS


def test_the_verifiers_are_named_as_a_sequence_rather_than_one_string(command: Any) -> None:
    """A single name reads as though it could never have been plural, and
    Session 9 adds agent-facing verifiers."""
    assert isinstance(command.VERIFIERS, tuple)
    assert command.VERIFIERS


def test_the_key_set_is_read_where_the_container_reads_it(command: Any) -> None:
    """One constant, so the path a verifier is configured with and the path this
    command inspects cannot drift."""
    assert command.VERIFIER_JWKS_PATH == runtime_override.JWKS_CONTAINER_PATH


def test_the_overlap_allows_for_the_verifiers_measured_leeway(command: Any) -> None:
    """D241 measured the locked PostgREST accepting a token 30 seconds past
    `exp`, bisected -- 30s served, 31s refused. A window computed from the TTL
    alone retires the old key while tokens it signed are still accepted."""
    assert command.CLOCK_SKEW_SECONDS >= 30
    assert command.MAX_TOKEN_TTL_SECONDS >= 1


# ---------------------------------------------------------------------------
# Where an acknowledgement comes from
# ---------------------------------------------------------------------------


def test_the_digest_is_read_from_inside_the_container(command: Any) -> None:
    """Asserted on the source, because this is the property the whole step is.

    A `docker exec ... cat` reads what the process has. A read of the host path
    reads what the deploy wrote, and after an atomic replace those are two
    different files -- so a command written the second way would report every
    verifier as current no matter what it held.
    """
    tree = ast.parse(COMMAND.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "loaded_digest"
    )
    body = ast.dump(function)
    assert "'docker'" in body and "'exec'" in body, (
        "the digest is not read from inside the container"
    )
    assert "read_bytes" not in body and "read_text" not in body, (
        "the digest is read from the host's copy of the key set, which after an atomic "
        "replace is not the file the verifier has open"
    )


def test_the_container_is_found_by_label_rather_than_predicted(command: Any) -> None:
    """`naming` predicts Compose's container name and the model deliberately does
    not enforce it with `container_name:` (D55). A command that built the name
    would depend on a convention this repository has chosen not to depend on."""
    tree = ast.parse(COMMAND.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "container_for"
    )
    body = ast.dump(function)
    assert "apg.project.key" in body
    assert "com.docker.compose.service" in body


# ---------------------------------------------------------------------------
# The refusals, as an operator meets them
# ---------------------------------------------------------------------------


def test_a_deployment_with_no_issuer_is_refused(command: Any, tmp_path: Path) -> None:
    path = tmp_path / "outputs.json"
    path.write_text(json.dumps({"jwt": {"status": "unavailable"}}), encoding="utf-8")
    with pytest.raises(command.OperatorError) as raised:
        command.key_state(json.loads(path.read_text(encoding="utf-8")))
    assert raised.value.code == command.EXIT_STATE
    assert "no issuer" in str(raised.value)


def test_promotion_is_refused_when_no_key_is_prepared(command: Any) -> None:
    steady = document()
    with pytest.raises(command.OperatorError, match="prepare a rotation first"):
        command.promote(None, Path("unused"), steady, command.key_state(steady))


def test_promotion_is_refused_when_a_verifier_has_not_acknowledged(command: Any) -> None:
    """The refusal the whole design exists for, reached through the command
    rather than through `jwt_keys` -- so a caller that passed the wrong
    `consumers` or the wrong digest would be visible here."""
    prepared = prepared_document()
    with pytest.raises(jwt_keys.JwkError, match="have not acknowledged"):
        command.promote(None, Path("unused"), prepared, command.key_state(prepared))


def test_promotion_proceeds_once_every_verifier_has_acknowledged(command: Any) -> None:
    """The control for the test above: the same call, with the record in place.

    Without this, a `promote` that refused unconditionally would pass every
    refusal test in this file.
    """
    prepared = prepared_document()
    state = command.key_state(prepared)
    for verifier in command.VERIFIERS:
        state = jwt_keys.record_acknowledgement(state, consumer=verifier, jwks_sha256=PUBLISHED)

    promoted = command.promote(
        None, Path("unused"), {**prepared, "jwt": {**prepared["jwt"]}}, state
    )
    assert promoted["active_kid"] != state["active_kid"]
    assert promoted["retire_after"] is not None


def test_an_acknowledgement_of_the_wrong_digest_does_not_unblock_promotion(command: Any) -> None:
    """A verifier that reloaded *something* is not a verifier that reloaded this.

    This is the case the command records rather than refuses: `acknowledge`
    writes what the verifier holds even when it disagrees, because a step that
    refused to write a disagreeing digest would leave the document silent where
    the truth is "this one is behind".
    """
    prepared = prepared_document()
    state = command.key_state(prepared)
    for verifier in command.VERIFIERS:
        state = jwt_keys.record_acknowledgement(state, consumer=verifier, jwks_sha256="d" * 64)

    with pytest.raises(jwt_keys.JwkError, match="have not acknowledged"):
        command.promote(None, Path("unused"), prepared, state)


def test_a_promoted_rotation_cannot_be_abandoned(command: Any) -> None:
    prepared = prepared_document()
    state = command.key_state(prepared)
    for verifier in command.VERIFIERS:
        state = jwt_keys.record_acknowledgement(state, consumer=verifier, jwks_sha256=PUBLISHED)
    promoted = command.promote(None, Path("unused"), prepared, state)

    with pytest.raises(jwt_keys.JwkError, match="complete it forward"):
        command.abandon(None, Path("unused"), prepared, promoted)


# ---------------------------------------------------------------------------
# What the command does NOT do
# ---------------------------------------------------------------------------


def test_no_step_writes_a_provider_value(command: Any) -> None:
    """D249's rule, held at the one command most tempted to break it.

    `bootstrap-providers.sh --apply` creates what is missing and deliberately
    leaves existing values alone, so a rotation's provider step is done by hand.
    A `prepare` here would be the first command in this repository to write a
    secret value, and it would do it during the one operation that cannot be
    undone.
    """
    source = COMMAND.read_text(encoding="utf-8")
    assert "prepare" not in {
        node.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)
    }
    for forbidden in ("infisical", "InfisicalClient", "set_secret", "provider_key="):
        assert forbidden not in source, f"the command reaches the provider via {forbidden!r}"


def test_the_command_prints_no_key_material(command: Any) -> None:
    """Every value this command handles is public -- kids and digests -- and it
    must stay that way even as messages grow. A `pem`, a `private` or a `-----
    BEGIN` in an f-string is a signing key in a deploy log."""
    source = COMMAND.read_text(encoding="utf-8")
    for forbidden in ("BEGIN RSA", "BEGIN PRIVATE", "read_bytes()", ".pem"):
        assert forbidden not in source, f"the command handles private material via {forbidden!r}"
