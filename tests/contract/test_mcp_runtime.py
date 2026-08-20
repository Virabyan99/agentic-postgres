"""The agent plane's runtime and the fourth verifier (Session 8, Run 4).

Three properties, and each one is here because something in this repository's
history says it would otherwise be assumed:

1. **The runtime is handed a key set, from the rendered file, by path.** D381 is
   the standing lesson -- storage was declared the third verifier in four places
   and given nothing to verify with, and the offline suite was green throughout
   because the two lists that could have disagreed *agreed*, both incomplete
   (D332). So the assertions here are against BEHAVIOUR and against the RENDERED
   artefacts, never against a second list.

2. **It holds no credential.** Not "does not use one" -- `settings.load_mcp`
   refuses to start when handed one, which is what makes D407's zero share of
   the connection budget a decision rather than an oversight.

3. **It accepts only agent tokens, and refuses before any lookup** (ADR 0115).

The framework is imported for real. A mocked FastMCP would be a test about the
mock (ADR 0065, and this repository has paid for that lesson often enough that
`requirements-dev.in` explains it twice).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_postgres import jwt_keys, runtime_override
from app import claims as claim_contract
from app import mcp_runtime
from app import settings as settings_module
from app.mcp_runtime import AgentTokenVerifier, verify_agent_claims
from app.tokens import LocalKeySet

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ISSUER = "https://example.test/api/app/auth"
AUDIENCE = "urn:agentic-postgres:example:dev"
AGENT_ROLE = "apg_example_dev_agent_reader"


# ---------------------------------------------------------------------------
# fixtures: a real key, a real rendered JWKS, a real signed token
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def signing_key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def rendered_jwks(tmp_path: Path, signing_key: Any) -> Path:
    """A file byte-shaped the way `bin/render-jwks.py` writes one.

    Built through `jwt_keys` -- the PLATFORM producer -- rather than through
    `app.keys`, because the pair this runtime actually exercises is
    `jwt_keys.build_jwks` -> `LocalKeySet.from_path`, and a test that used the
    service's own producer would be exercising the half that already worked.
    """
    numbers = signing_key.public_key().public_numbers()
    document = jwt_keys.build_jwks(
        [jwt_keys.public_jwk(modulus_hex=format(numbers.n, "X"), exponent=numbers.e)]
    )
    path = tmp_path / "jwks.json"
    path.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return path


def _claims(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "0d9c0a24-6b1a-4f5e-9a5e-2b6a1e9f0c31",
        "role": AGENT_ROLE,
        "scope": ["notes:read", "tasks:read"],
        "token_use": "agent",
        "jti": "b7a1c2d3e4f5",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "credential_version": 1,
        "authz_version": 1,
    }
    payload.update(overrides)
    return payload


def _token(signing_key: Any, rendered_jwks: Path, **overrides: Any) -> str:
    """A token signed by the key the rendered set publishes, with the right kid."""
    document = json.loads(rendered_jwks.read_text(encoding="utf-8"))
    kid = document["keys"][0]["kid"]
    pem = signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(
        _claims(**overrides),
        pem,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )


def _verify(verifier: AgentTokenVerifier, token: str) -> Any:
    return asyncio.run(verifier.verify_token(token))


@pytest.fixture
def verifier(rendered_jwks: Path) -> AgentTokenVerifier:
    return AgentTokenVerifier(
        LocalKeySet.from_path(rendered_jwks), issuer=ISSUER, audience=AUDIENCE
    )


# ---------------------------------------------------------------------------
# the fourth verifier: it reads the rendered file, by path
# ---------------------------------------------------------------------------


def test_the_agent_plane_verifies_a_token_against_the_rendered_key_set(
    verifier: AgentTokenVerifier, signing_key: Any, rendered_jwks: Path
) -> None:
    """The whole path, end to end, with nothing stubbed.

    A key rendered by the platform producer, written to a file the way
    `render-jwks.py` writes one, read by `LocalKeySet.from_path`, and used to
    verify a token signed by the matching private half. This is the link D381
    proves nothing else exercises.
    """
    granted = _verify(verifier, _token(signing_key, rendered_jwks))

    assert granted is not None, "a correctly signed agent token was refused"
    assert granted.subject == _claims()["sub"]
    assert granted.scopes == ["notes:read", "tasks:read"]
    assert granted.claims["token_use"] == "agent"  # noqa: S105 -- a claim VALUE, not a credential


def test_a_token_signed_by_another_key_is_refused(
    verifier: AgentTokenVerifier, rendered_jwks: Path
) -> None:
    """**The control for the test above.**

    Without it, a verifier that returned a principal for anything at all would
    pass every acceptance test in this module. A different RSA key, the same
    `kid`: so this is the SIGNATURE being checked, not the key lookup.
    """
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    assert _verify(verifier, _token(other, rendered_jwks)) is None


def test_a_token_naming_an_unpublished_kid_is_refused_rather_than_tried(
    verifier: AgentTokenVerifier, signing_key: Any, rendered_jwks: Path
) -> None:
    """No fallback across keys.

    Trying every key is how a retired key keeps verifying tokens for as long as
    it is still published -- exactly the window `retire` exists to close.
    """
    pem = signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    stranger = jwt.encode(
        _claims(), pem, algorithm="RS256", headers={"kid": "not-in-the-set", "typ": "JWT"}
    )

    assert _verify(verifier, stranger) is None


def test_the_runtime_reads_the_same_rendered_artefact_the_other_verifiers_read(
    tmp_path: Path,
) -> None:
    """One file, mounted at the agent plane's own path (ADR 0113, ADR 0121).

    Asserted against the RENDERED override rather than against a constant, so a
    mount that stopped being emitted fails here even though both constants still
    agree with each other (D332).
    """
    from tests.contract.test_runtime_override import NAMES, RENDERED

    override = runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )
    mounts = override["services"][runtime_override.MCP_SERVICE]["volumes"]

    assert mounts == [
        f"{RENDERED}/{runtime_override.JWKS_FILENAME}:{runtime_override.MCP_JWKS_CONTAINER_PATH}:ro"
    ]

    postgrest = override["services"][runtime_override.REST_SERVICE]["volumes"]
    host_sides = {mount.split(":", 1)[0] for mount in mounts + postgrest}
    assert host_sides == {f"{RENDERED}/{runtime_override.JWKS_FILENAME}"}, (
        "the agent plane must read the SAME rendered file the REST verifier reads, "
        "not a copy of it (D264)"
    )


# ---------------------------------------------------------------------------
# ADR 0115: only agent tokens, refused before any lookup
# ---------------------------------------------------------------------------


def test_an_access_token_is_refused_at_the_agent_plane(
    verifier: AgentTokenVerifier, signing_key: Any, rendered_jwks: Path
) -> None:
    """ADR 0115's whole content, against a token that is otherwise perfect.

    Correctly signed, in date, sorted scopes, a real role -- and `token_use:
    "access"`. It is ADR 0114's mirror and the two must not overlap.
    """
    access = _token(signing_key, rendered_jwks, token_use="access")  # noqa: S106 -- a claim VALUE

    assert _verify(verifier, access) is None


def test_the_two_planes_accept_different_token_uses() -> None:
    """The mirror, asserted as a relation rather than as two literals.

    `mcp_runtime.ACCEPTED_TOKEN_USE` and the application API's accepted use are
    both real values; a test naming them separately would pass if somebody set
    them to the same string.
    """
    assert mcp_runtime.ACCEPTED_TOKEN_USE in claim_contract.TOKEN_USES
    assert mcp_runtime.ACCEPTED_TOKEN_USE != "access"  # noqa: S105 -- a claim VALUE, not a credential


@pytest.mark.parametrize(
    ("override", "why"),
    [
        ({"token_use": "access"}, "ADR 0115: the application API's token use"),
        ({"authz_version": 0}, "below the schema's own CHECK (authz_version >= 1)"),
        ({"scope": ["tasks:read", "notes:read"]}, "the issuer sorts before signing"),
        ({"scope": ["notes:read", "notes:read"]}, "a repeated scope"),
        ({"iss": "https://elsewhere.test"}, "another issuer"),
        ({"aud": "urn:somebody:else"}, "another audience"),
        ({"sub": "   "}, "a blank agent id"),
    ],
)
def test_the_claim_contract_refuses(override: dict[str, Any], why: str) -> None:
    """Each refusal, over the pure function, so the reason is visible.

    `verify_agent_claims` takes a payload rather than a token, which is what
    makes these seven cases assertable at all -- through the verifier they would
    every one of them be an indistinguishable `None`.
    """
    with pytest.raises(claim_contract.ClaimError):
        verify_agent_claims(
            _claims(**override), issuer=ISSUER, audience=AUDIENCE, now=int(time.time())
        )


def test_the_claim_contract_accepts_a_good_payload() -> None:
    """**The control for the parametrised refusals above.**

    Without it, a `verify_agent_claims` that raised unconditionally would pass
    all seven. Session 8 Run 1 and Run 3 both had a battery arm that needed
    exactly this, and CLAUDE.md §1 says why.
    """
    verified = verify_agent_claims(
        _claims(), issuer=ISSUER, audience=AUDIENCE, now=int(time.time())
    )

    assert verified["token_use"] == "agent"  # noqa: S105 -- a claim VALUE, not a credential
    assert verified["authz_version"] >= mcp_runtime.MINIMUM_AUTHZ_VERSION


def test_the_shared_claim_contract_was_not_weakened_to_admit_the_agent_floor() -> None:
    """The agent plane's floor is ADDITIVE (CLAUDE.md §5).

    `claims.verify_claims` still accepts `authz_version: 0` -- it is the shared
    contract, and the application API's rules did not change to make Run 4's
    pass. If somebody ever tightens it there, this test is the one that says the
    decision was made in the wrong place.
    """
    permitted = claim_contract.verify_claims(
        _claims(authz_version=0), issuer=ISSUER, audience=AUDIENCE, now=int(time.time())
    )

    assert permitted["authz_version"] == 0

    with pytest.raises(claim_contract.ClaimError):
        verify_agent_claims(
            _claims(authz_version=0), issuer=ISSUER, audience=AUDIENCE, now=int(time.time())
        )


# ---------------------------------------------------------------------------
# D407: it holds no credential, and that is enforced rather than observed
# ---------------------------------------------------------------------------


def _mcp_environment(**extra: str) -> dict[str, str]:
    environment = {
        "APG_PROJECT_KEY": "example-dev",
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": ISSUER,
        "APG_JWT_AUDIENCE": AUDIENCE,
        "APG_JWKS_FILE": "/etc/mcp/jwks.json",
        "APG_LISTEN_PORT": "8080",
    }
    environment.update(extra)
    return environment


def test_the_agent_plane_loads_from_exactly_its_declared_variables() -> None:
    """`MCP_VARIABLES` is what `load_mcp` reads, proved by reading them."""
    loaded = settings_module.load_mcp(_mcp_environment())

    assert loaded.project_key == "example-dev"
    assert loaded.jwks_file == Path("/etc/mcp/jwks.json")
    assert set(settings_module.MCP_VARIABLES) == set(_mcp_environment())


@pytest.mark.parametrize("forbidden", settings_module.FORBIDDEN_VARIABLES["mcp"])
def test_a_credential_in_the_agent_planes_environment_refuses_the_start(
    forbidden: str,
) -> None:
    """Refused, not ignored -- the same shape as storage refusing a signing key.

    Parametrised over the constant so a variable added to the forbidden set is
    automatically proved, and a variable REMOVED from it loses its test loudly
    rather than quietly.
    """
    with pytest.raises(settings_module.MissingSetting):
        settings_module.load_mcp(_mcp_environment(**{forbidden: "something"}))


def test_the_agent_plane_is_given_no_database_settings_at_all() -> None:
    """The absence, stated as a property of the type rather than of a comment.

    `McpSettings` has no `conninfo`, no pool size and no passfile, so there is
    nothing for a later change to fill in by accident. D407's considered zero in
    the connection budget rests on this.
    """
    fields = set(settings_module.McpSettings.__dataclass_fields__)

    assert not fields & {"database_host", "database_role", "passfile", "pool_size"}
    assert not hasattr(settings_module.McpSettings, "conninfo")


def test_the_agent_plane_is_absent_from_the_post_bootstrap_services(self=None) -> None:
    """D410, and the reason: it authenticates as no role to be activated."""
    assert runtime_override.MCP_SERVICE not in runtime_override.POST_BOOTSTRAP_SERVICES
    assert runtime_override.STORAGE_SERVICE in runtime_override.POST_BOOTSTRAP_SERVICES


def test_settings_load_refuses_the_agent_plane_mode() -> None:
    """`Settings` is the auth and storage shape, and says so.

    Falling through would take the `else` branch and demand a SIGNING KEY of the
    one runtime furthest from being an issuer.
    """
    assert "mcp" in settings_module.APP_MODES

    with pytest.raises(settings_module.MissingSetting, match="load_mcp"):
        settings_module.load(_mcp_environment(), mode="mcp")


# ---------------------------------------------------------------------------
# ADR 0123: the protocol revision comes from the framework
# ---------------------------------------------------------------------------


def test_the_protocol_revision_is_the_frameworks_and_not_a_literal() -> None:
    """Read from `mcp.types`, never written down here (ADR 0123, D406).

    The assertion is the IDENTITY with the framework's constant plus the shape,
    rather than a date this test would have to be edited to keep true -- which
    would be two constants compared to each other, and this repository has been
    caught by that one already.
    """
    from mcp.types import LATEST_PROTOCOL_VERSION

    assert mcp_runtime.PROTOCOL_REVISION == LATEST_PROTOCOL_VERSION

    year, month, day = mcp_runtime.PROTOCOL_REVISION.split("-")
    assert (len(year), len(month), len(day)) == (4, 2, 2)
    assert year.isdigit() and month.isdigit() and day.isdigit()


def test_the_published_revision_is_not_the_default_negotiated_one() -> None:
    """The neighbouring trap, named so it cannot be adopted by mistake.

    `DEFAULT_NEGOTIATED_VERSION` is what an unversioned caller receives, and it
    is below the ceiling this runtime speaks. A test asserting only the shape
    would accept it, because it has the same shape.
    """
    from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
    from mcp.types import DEFAULT_NEGOTIATED_VERSION

    assert mcp_runtime.PROTOCOL_REVISION != DEFAULT_NEGOTIATED_VERSION
    assert mcp_runtime.PROTOCOL_REVISION == max(SUPPORTED_PROTOCOL_VERSIONS)


def test_the_agent_plane_declares_its_bearer_profile_non_conformant() -> None:
    """D413: the honesty is the valuable part, and it is a FIELD not prose."""
    assert mcp_runtime.AUTHORIZATION_SPEC_CONFORMANT is False
