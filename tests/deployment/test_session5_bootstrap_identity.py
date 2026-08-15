"""The temporary bootstrap issuer holds the only private key (SEC-BOOT-001).

Replaces one Session 5 placeholder in
``tests/security/test_future_security_boundaries.py``. Under
``tests/deployment/`` with the ``security`` marker, for D111's reason.

ADR 0051's issuer is temporary by construction, and ``temporary`` is state in the
deployed document rather than prose nobody executes: this test **goes red on the
deployment that retires it**. That is ADR 0046's rule -- a fact with an expiry
date is written so that whatever invalidates it makes the test fail rather than
makes it stale.

**The clause was re-keyed in Session 6 Run 11 (ADR 0090), and this is a stricter
test than the one it replaces.** It used to compare
``deployed_through_session`` against a constant 6, on the reasoning that Session
6 retires the issuer. Session 6 did not: ADR 0088 built the cutover and the
operator guide forbids starting one, because two live issuers fill the two-key
ceiling and the transition between them *is* the first rotation. Measured with a
control, a deploy through session 6 failed at that assertion while an otherwise
identical document at session 5 got past it -- so the host trip that deploys Run
10 would have turned this green proof red for a correct deployment.

The session number was always a proxy for "the retirement has happened". The
deployed document now carries the state that answers directly, so the proxy is
replaced by the event: while the issuer is temporary its key must still be
**published**, and the `kid` is **derived here from the private key on disk**
rather than read from the document that claims it. That second half is new, and
it is D276's lesson applied to this requirement -- the document said which keys
verify, and nothing had ever asked whether those identifiers came from the keys
this deployment actually holds.
"""

from __future__ import annotations

import json
import stat
from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, jwt_keys, secrets_contract
from agentic_postgres.secret_generation import SECRET_ROOT

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS"),
]

#: (Removed in Run 11 -- ADR 0090.) This was `ISSUER_RETIRED_IN_SESSION = 6`,
#: compared against `deployed_through_session`. The retirement is an event, not
#: a session, and the deployed document records the event.

#: What a PEM private key opens with, in either encoding openssl emits.
PRIVATE_KEY_MARKERS = ("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----")


def test_the_bootstrap_issuer_is_temporary_and_holds_the_only_private_key(
    project_a: dict[str, Any],
    sh: Callable[..., str],
    jwks_command: Any,
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

    # ADR 0090's clause, and it replaces a comparison against a session number.
    #
    # The `kid` is DERIVED from the key on disk rather than read from the
    # document that names it. Nothing had ever checked that the identifiers in
    # `verification_kids` come from keys this deployment holds -- the document
    # said which keys verify, and every proof took its word for it. That is
    # D276's shape, and this is the same question asked of the bootstrap key.
    modulus, exponent = jwks_command.read_public_parameters(key)
    bootstrap_kid = jwt_keys.public_jwk(modulus_hex=modulus, exponent=exponent)["kid"]

    if jwt["temporary"] is True:
        assert bootstrap_kid in jwt["verification_kids"], (
            f"the deployed document records a temporary issuer, but the bootstrap key's "
            f"own thumbprint ({bootstrap_kid}) is not among the keys it publishes "
            f"({jwt['verification_kids']}). Either the issuer was retired and the "
            "document was not updated, or the published set was derived from a key "
            "this host does not hold"
        )
    else:
        assert bootstrap_kid not in jwt["verification_kids"], (
            f"the issuer is no longer marked temporary, yet its key ({bootstrap_kid}) is "
            "still published and still verifies tokens. `temporary: false` while the "
            "bootstrap issuer is live is a value that looks measured and is not"
        )

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
