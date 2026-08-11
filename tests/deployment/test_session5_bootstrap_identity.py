"""The temporary bootstrap issuer holds the only private key (SEC-BOOT-001).

Replaces one Session 5 placeholder in
``tests/security/test_future_security_boundaries.py``. Under
``tests/deployment/`` with the ``security`` marker, for D111's reason.

ADR 0051's issuer is temporary by construction, and ``temporary`` is state in the
deployed document rather than prose nobody executes: this test compares it
against ``deployed_through_session`` and **goes red on the deployment that should
have replaced it**. That is ADR 0046's rule -- a fact with an expiry date is
written so the session which invalidates it makes the test fail rather than makes
it stale.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, secrets_contract
from agentic_postgres.secret_generation import SECRET_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: The session that retires the bootstrap issuer (ADR 0051). A deployment
#: through this session or later must no longer be running on a temporary one.
ISSUER_RETIRED_IN_SESSION = 6

#: What a PEM private key opens with, in either encoding openssl emits.
PRIVATE_KEY_MARKERS = ("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----")


def test_the_bootstrap_issuer_is_temporary_and_holds_the_only_private_key(
    project_a: dict[str, Any],
    sh: Callable[..., str],
    as_root: None,
) -> None:
    """SEC-BOOT-001, in the four places the private key could be.

    **The document.** ``jwt.temporary`` is true, the algorithm is asymmetric, and
    the block carries key *identifiers* and a JWKS digest -- never a private JWK,
    never a reference to one. RS256 rather than a symmetric algorithm is the
    whole property: a shared secret would make every verifier an issuer.

    **The filesystem.** The key is materialized into the root plane, 0400 owned
    by root. That is what makes "no service holds it" a property of the
    filesystem rather than of a policy, and it is why every command that signs
    needs ``sudo``.

    **The other generations' directories.** Every per-consumer copy is checked
    for PEM material, because the failure this catches is a materializer that
    wrote the key to the consumers of some *other* secret.

    **The containers.** No running container may carry the key in its
    environment, its mounts or its command. Read from ``docker inspect`` rather
    than from the Compose model, for the reason ``SEC-DOCS-001`` records: the
    model says what was asked for.

    Goes red if: the signing key gains a ``plane: compose`` consumer; its mode is
    relaxed; the algorithm becomes symmetric, which would put signing material in
    every verifier; the deployed document starts carrying private key material;
    or a project is deployed through session 6 or later while still recording a
    temporary issuer -- the clause that makes this expire rather than go stale.
    """
    del as_root
    jwt = project_a.get("jwt") or {}
    assert jwt.get("status") == "ready", (
        f"the deployed document reports jwt.status={jwt.get('status')!r}; there is no "
        "issuer here to characterise"
    )

    assert jwt["algorithm"] == "RS256", (
        f"the issuer signs with {jwt['algorithm']!r}. A symmetric algorithm makes every "
        "verifier an issuer, which is the property ADR 0051 refuses"
    )
    assert jwt["temporary"] is True, "the bootstrap issuer is not marked temporary"
    assert project_a["deployed_through_session"] < ISSUER_RETIRED_IN_SESSION, (
        f"this project is deployed through session {project_a['deployed_through_session']} "
        f"and still records a temporary issuer. Session {ISSUER_RETIRED_IN_SESSION} "
        "replaces it (ADR 0051); this assertion is what was written to fail here rather "
        "than to go quietly out of date"
    )
    assert jwt["active_kid"] in jwt["verification_kids"], (
        "the active key id is not among the verification key ids, so nothing verifies "
        "what this issuer signs"
    )

    serialized = json.dumps(jwt)
    for marker in PRIVATE_KEY_MARKERS:
        assert marker not in serialized, "the deployed document carries private key material"

    contract = secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    declared = [
        secret for secret in contract["secrets"] if secret["name"] == "bootstrap_jwt_signing_key"
    ]
    assert declared, "the secrets contract declares no bootstrap_jwt_signing_key"
    planes = {consumer["plane"] for consumer in declared[0]["consumers"]}
    assert planes == {"root"}, (
        f"the signing key declares consumers in {sorted(planes)}; a compose consumer is "
        "a container that can sign tokens for this issuer"
    )

    generation = (
        SECRET_ROOT
        / project_a["project"]["key"]
        / "generations"
        / (project_a["secrets"]["generation_id"])
    )
    key = generation / secrets_contract.ROOT_PLANE_DIRECTORY / "bootstrap_jwt_signing_key.pem"
    assert key.is_file(), f"no signing key at {key}"

    mode = key.stat()
    assert stat.S_IMODE(mode.st_mode) == 0o400, (
        f"{key} is {stat.S_IMODE(mode.st_mode):04o}, not 0400"
    )
    assert (mode.st_uid, mode.st_gid) == (0, 0), f"{key} is owned by {mode.st_uid}:{mode.st_gid}"

    for path in sorted(generation.rglob("*")):
        if not path.is_file() or path == key:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for marker in PRIVATE_KEY_MARKERS:
            assert marker not in content, f"private key material was materialized into {path}"

    names = [line for line in sh("docker", "ps", "--format", "{{.Names}}").splitlines() if line]
    assert names, "no containers are running, so nothing here was inspected"
    for name in names:
        inspected = sh("docker", "inspect", name)
        for marker in PRIVATE_KEY_MARKERS:
            assert marker not in inspected, f"{name} holds private key material"
        assert str(key) not in inspected, (
            f"{name} mounts or names the signing key at {key}; a verifier that can reach "
            "the private key is an issuer"
        )
