"""Where each runtime's verification key set comes from (ADR 0113).

**D381 is what this module exists to make impossible.** Storage was declared the
third verifier in ADR 0098, D320, `compose.yaml` and `main.py`, and was handed no
verification material of any kind: `AuthService` derived its only key set from
the signing key, which storage mode sets to `None` deliberately. The container
raised `AttributeError: 'NoneType' object has no attribute 'jwks'` and uvicorn
exited 3 on its first start on any host.

The offline suite was green throughout, because the two artefacts that could
have disagreed -- `STORAGE_VARIABLES` and `compose.yaml` -- **agreed**, and
neither named a verification key. Two incomplete lists satisfy a test that
compares them to each other (D332). So the tests here assert against *behaviour*
and against the *rendered* artefacts, not against a second list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from tests.contract.test_runtime_override import NAMES, RENDERED

from agentic_postgres import jwt_keys, runtime_override
from app import settings as settings_module
from app.service import AuthService
from app.tokens import LocalKeySet

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture
def rendered_override() -> dict[str, Any]:
    return runtime_override.build_override(
        **NAMES, https_entrypoint="websecure", rendered_directory=RENDERED
    )


def _public_jwk() -> dict[str, str]:
    """A JWK built by the PLATFORM producer -- the one `render-jwks.py` uses.

    Deliberately not `app.keys.SigningKey.jwks()`. Two modules build this
    document, and the pair that had never been exercised together is
    `jwt_keys` -> `LocalKeySet`: the file storage reads is written by the
    platform and parsed by the service.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    return jwt_keys.public_jwk(modulus_hex=format(numbers.n, "X"), exponent=numbers.e)


def _rendered_jwks(tmp_path: Path, count: int = 2) -> Path:
    """A file byte-shaped the way `bin/render-jwks.py` writes one."""
    document = jwt_keys.build_jwks([_public_jwk() for _ in range(count)])
    path = tmp_path / "jwks.json"
    path.write_bytes(json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return path


# -- the defect itself ----------------------------------------------------


def test_a_verifier_only_runtime_builds_with_no_signing_key(tmp_path: Path) -> None:
    """**The test that would have caught D381.**

    Nothing in the suite had ever constructed the service the way storage mode
    constructs it: `signing_key=None`. Every existing construction passed a real
    key, so the one line that dereferenced it was covered by every test and
    exercised by none of them in the configuration that ships.
    """
    key_set = LocalKeySet.from_path(_rendered_jwks(tmp_path))

    service = AuthService(
        repository=object(),  # type: ignore[arg-type]
        hasher=object(),  # type: ignore[arg-type]
        signing_key=None,
        key_set=key_set,
        issuer="https://example.test",
        audience="apg",
        role_suffixes={},
    )

    assert service.signing_key is None
    assert len(service.key_set.keys) == 2, "the verifier holds the set it was given"


def test_the_platform_producer_and_the_service_parser_agree(tmp_path: Path) -> None:
    """The link the fix rests on, measured rather than assumed.

    `jwt_keys.build_jwks` writes the document; `LocalKeySet` reads it. Before
    ADR 0113 nothing put the two together -- `from_path`'s only caller in the
    repository was a test using a hand-written document.
    """
    path = _rendered_jwks(tmp_path)
    key_set = LocalKeySet.from_path(path)

    republished = json.loads(key_set.as_document())["keys"]
    assert len(republished) == 2
    for entry in republished:
        assert entry["kty"] == "RSA"
        assert entry["alg"] == "RS256"
        assert entry["kid"], "RFC 7638 thumbprint, computed by the producer"
        assert "d" not in entry, "public material only"


def test_a_verifier_only_runtime_refuses_to_issue(tmp_path: Path) -> None:
    """It cannot sign, and says so rather than raising AttributeError.

    `/auth/login` is not mounted in storage mode, so there is no caller. The
    check exists because D381's signature in a log was exactly an
    `AttributeError` on a `None`, and a named invariant is readable where that
    is not.
    """
    service = AuthService(
        repository=object(),  # type: ignore[arg-type]
        hasher=object(),  # type: ignore[arg-type]
        signing_key=None,
        key_set=LocalKeySet.from_path(_rendered_jwks(tmp_path)),
        issuer="https://example.test",
        audience="apg",
        role_suffixes={},
    )

    # The real entry point, refusing before it touches the credential -- which
    # is why a bare object suffices as the argument.
    # (S106 matches on the argument name. "access" is a token_use discriminator
    # from the claim contract, not a secret -- the same noqa `service.py` carries.)
    with pytest.raises(RuntimeError, match="holds no signing key"):
        service.issue(object(), token_use="access")  # type: ignore[arg-type]  # noqa: S106


# -- the settings contract ------------------------------------------------


def _storage_environ(tmp_path: Path) -> dict[str, str]:
    return {
        "APG_PROJECT_KEY": "alpha-dev",
        "APG_PROJECT_ENVIRONMENT": "dev",
        "APG_JWT_ISSUER": "https://example.test",
        "APG_JWT_AUDIENCE": "apg",
        "APG_DATABASE_HOST": "pgbouncer",
        "APG_DATABASE_PORT": "5432",
        "APG_DATABASE_NAME": "alpha_dev",
        "APG_DATABASE_ROLE": "apg_alpha_dev_storage_service",
        "APG_DATABASE_PASSFILE": "/run/secrets/storage_service_pgpass",
        "APG_POOL_SIZE": "6",
        "APG_LISTEN_PORT": "8080",
        "APG_ROLE_NAMES": '{"anon": "apg_alpha_dev_anon"}',
        "APG_JWKS_FILE": str(tmp_path / "jwks.json"),
        "APG_STORAGE_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
        "APG_STORAGE_BUCKET": "apg-alpha-dev",
        "APG_STORAGE_PREFIX": "objects/alpha-dev/",
        "APG_STORAGE_ACCESS_KEY_ID_FILE": "/run/secrets/r2_access_key_id",
        "APG_STORAGE_SECRET_ACCESS_KEY_FILE": "/run/secrets/r2_secret_access_key",
        "APG_STORAGE_UPLOAD_URL_TTL_SECONDS": "900",
        "APG_STORAGE_DOWNLOAD_URL_TTL_SECONDS": "300",
        "APG_STORAGE_MAX_UPLOAD_BYTES": "1048576",
    }


def test_storage_mode_requires_a_key_set_source(tmp_path: Path) -> None:
    """Absent, it would verify nothing -- and it would START.

    That is why this is required rather than optional. A container that comes
    up and refuses every token looks deployed; D381 at least failed loudly.
    """
    environ = _storage_environ(tmp_path)
    # `.pop`, not `del environ[...]`, for the reason
    # `test_storage_endpoints.py` records: the environment scanner counts any
    # subscript with an `APG_`-prefixed string constant as a real environment
    # read. It is deliberately broad and right to be; this dict is one the test
    # built, so the fix belongs here rather than in the scanner.
    environ.pop("APG_JWKS_FILE")

    with pytest.raises(settings_module.MissingSetting, match="APG_JWKS_FILE"):
        settings_module.load(environ, mode="storage")


def test_storage_mode_reads_the_key_set_path(tmp_path: Path) -> None:
    settings = settings_module.load(_storage_environ(tmp_path), mode="storage")

    assert settings.jwks_file == tmp_path / "jwks.json"
    assert settings.signing_key_file is None, "a verifier is granted no signing key"


def test_auth_mode_refuses_a_second_key_set(tmp_path: Path) -> None:
    """An issuer verifies with what it signs with (ADR 0098).

    The mirror of storage's refusal of a signing key. Two sources for one key
    set is two authorities for one value (D264), and the failure mode is an
    issuer minting tokens its own verifier rejects.
    """
    environ = {
        k: v for k, v in _storage_environ(tmp_path).items() if not k.startswith("APG_STORAGE_")
    }
    # `.update`, not a subscript assignment, for the same scanner reason above.
    environ.update({"APG_SIGNING_KEY_FILE": str(tmp_path / "key.pem")})

    with pytest.raises(settings_module.MissingSetting, match="APG_JWKS_FILE"):
        settings_module.load(environ, mode="auth")


def test_each_mode_declares_its_own_key_set_source() -> None:
    """Neither list may quietly acquire the other's."""
    assert "APG_JWKS_FILE" in settings_module.STORAGE_VARIABLES
    assert "APG_JWKS_FILE" not in settings_module.REQUIRED_VARIABLES
    assert "APG_SIGNING_KEY_FILE" in settings_module.REQUIRED_VARIABLES
    assert "APG_SIGNING_KEY_FILE" not in settings_module.STORAGE_VARIABLES

    assert "APG_JWKS_FILE" in settings_module.FORBIDDEN_VARIABLES["auth"]
    assert "APG_SIGNING_KEY_FILE" in settings_module.FORBIDDEN_VARIABLES["storage"]


# -- the rendered mount ---------------------------------------------------


def test_the_storage_service_is_mounted_the_rendered_key_set(
    rendered_override: dict[str, Any],
) -> None:
    """A variable naming a path proves nothing if no file is at that path.

    The environment says `/etc/storage/jwks.json`; this asserts something
    actually mounts the rendered file there. The pair is the whole content of
    the fix -- either half alone starts a container that cannot verify.
    """
    storage = rendered_override["services"][runtime_override.STORAGE_SERVICE]
    volumes = storage.get("volumes", [])

    mounted = [
        v for v in volumes if v.endswith(f"{runtime_override.STORAGE_JWKS_CONTAINER_PATH}:ro")
    ]
    assert len(mounted) == 1, f"expected one read-only JWKS mount, got {volumes}"

    source = mounted[0].split(":")[0]
    assert source.endswith(f"/{runtime_override.JWKS_FILENAME}")
    assert Path(source).is_absolute(), (
        "a relative source resolves against the RELEASE, so every project would "
        "mount one file -- the reason the REST mount lives in the override too"
    )


def test_both_verifiers_are_given_the_same_file(rendered_override: dict[str, Any]) -> None:
    """One artefact, two readers (ADR 0113).

    A second copy for storage would be a second authority for one value (D264),
    and the two verifiers could then disagree about which keys are live -- which
    is the exact failure ADR 0088's recreate step exists to prevent.
    """
    services = rendered_override["services"]
    rest_source = services[runtime_override.REST_SERVICE]["volumes"][0].split(":")[0]
    storage_source = services[runtime_override.STORAGE_SERVICE]["volumes"][0].split(":")[0]

    assert rest_source == storage_source, (
        "postgrest and storage must read the SAME rendered JWKS, not two copies"
    )
