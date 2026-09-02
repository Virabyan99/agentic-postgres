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
    or ``jwt.temporary`` disagrees with whether the key is actually materialized.

    **The temporary clause is real since Session 15 Run 1** (ADR 0170). It read
    *"a project deployed through session 6 or later while still recording a
    temporary issuer"* for ten sessions, and no such assertion existed: the deploy
    hard-coded ``temporary: True``, so the false branch was unreachable and the
    docstring described a check the body did not make. It is now a comparison
    against the filesystem, and both branches are live -- ``true`` before the
    retirement, ``false`` after it.
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

    # **The disk is the independent reading, and the document is compared against
    # it** (ADR 0170).
    #
    # `jwt.temporary` was the literal `True` for ten sessions -- under a comment
    # reading "True until Session 6 replaces the issuer", written before Session
    # 6 and never revisited after it shipped. So the false branch below had never
    # executed and the field described nothing. The deploy now reads it from the
    # contract's `retired_in_session`, and **this proof deliberately does not**:
    # a proof consulting the same declaration as the code under test would agree
    # with it however wrong both were. That is the sixth question, and D673,
    # D680 and D687 are what it costs.
    present = key.is_file()
    assert jwt["temporary"] is present, (
        f"the deployed document says temporary={jwt['temporary']!r} while the bootstrap "
        f"issuer's key is {'present' if present else 'absent'} at {key}. The field and "
        "the materialization disagree, so one of them describes a deployment that does "
        "not exist"
    )

    if present:
        mode = key.stat()
        assert stat.S_IMODE(mode.st_mode) == 0o400, (
            f"{key} is {stat.S_IMODE(mode.st_mode):04o}, not 0400"
        )
        assert (mode.st_uid, mode.st_gid) == (0, 0), (
            f"{key} is owned by {mode.st_uid}:{mode.st_gid}"
        )

        # ADR 0090's clause, replacing a comparison against a session number. The
        # `kid` is DERIVED from the key on disk rather than read from the
        # document that names it: nothing had ever checked that the identifiers
        # in `verification_kids` come from keys this deployment holds. D276's
        # shape, asked of the bootstrap key.
        modulus, exponent = jwks_command.read_public_parameters(key)
        bootstrap_kid = jwt_keys.public_jwk(modulus_hex=modulus, exponent=exponent)["kid"]
        assert bootstrap_kid in jwt["verification_kids"], (
            f"the bootstrap issuer's key is still materialized, but its own thumbprint "
            f"({bootstrap_kid}) is not among the keys this deployment publishes "
            f"({jwt['verification_kids']}). Either the key was retired and the document "
            "was not updated, or the published set was derived from a key this host "
            "does not hold"
        )
    else:
        # Retired. The key is gone, so its `kid` cannot be derived in order to
        # search for it -- the assertion is therefore about what the set IS
        # rather than what it lacks, which is the stronger claim anyway.
        auth_key = generation / jwks_command.AUTH_SERVICE / jwks_command.AUTH_SIGNING_KEY_FILE
        assert auth_key.is_file(), (
            f"the bootstrap issuer is retired and there is no auth signing key at "
            f"{auth_key} either. Nothing can sign a token this deployment verifies"
        )
        modulus, exponent = jwks_command.read_public_parameters(auth_key)
        auth_kid = jwt_keys.public_jwk(modulus_hex=modulus, exponent=exponent)["kid"]

        assert jwt["active_kid"] == auth_kid, (
            f"the retired issuer is gone but active_kid is {jwt['active_kid']!r}, which "
            f"is not the auth service's key ({auth_kid}). The document names an active "
            "key this host cannot produce"
        )
        assert auth_kid in jwt["verification_kids"]

        # **The slot D683 was blocked on.** Fewer published keys than the ceiling
        # means a rotation can be PREPARED, which is the entire result of the
        # retirement and was untrue for nine sessions. A full set is only
        # legitimate here while a rotation is actually in flight.
        assert (
            len(jwt["verification_kids"]) < jwt_keys.MAX_VERIFICATION_KEYS
            or jwt.get("retire_after") is not None
        ), (
            f"the published set is full at {jwt['verification_kids']} with no rotation "
            "in flight, so a rotation still cannot be prepared. Retiring the bootstrap "
            "issuer was supposed to free exactly this slot (D683)"
        )

    # The AUTH SERVICE's own signing key is not a leak of this one.
    #
    # This scan excluded exactly one file -- the bootstrap key -- and read every
    # other file in the generation for PEM markers. Session 6 gave the auth
    # service a signing key of its own, on the compose plane, 0400 to uid 65532,
    # and the scan reported it as "private key material was materialized into
    # ...". It is where it is supposed to be: the service IS an issuer
    # (ADR 0088), which is the whole reason `SEC-KEY-001` was rewritten
    # per-service in Session 6 -- and that proof asserts this file's mode and
    # location positively, so excluding it here loses no coverage (ADR 0096).
    #
    # What this proof still asserts is its own subject: no copy of the BOOTSTRAP
    # issuer's key exists outside the root plane. The exclusion names ONE path,
    # derived from the command that writes it, so a bootstrap key copied into
    # the auth service's directory under any other name is still found.
    permitted = {
        key,
        generation / jwks_command.AUTH_SERVICE / jwks_command.AUTH_SIGNING_KEY_FILE,
    }
    for path in sorted(generation.rglob("*")):
        if not path.is_file() or path in permitted:
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
