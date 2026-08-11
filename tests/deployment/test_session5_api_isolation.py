"""Two projects, two API planes, nothing shared (DEP-ISO-005).

Replaces one Session 5 placeholder in ``tests/contract/test_future_deployment.py``.

**The cross-project clause carries its own node ID**, and that is the whole
reason this module has two tests rather than one. D70 is the standing lesson:
``DEP-ISO-003`` claimed the same class of property for two runs behind six node
IDs, and not one of them presented a credential to anything. "The routes differ"
and "one project's token is refused by the other" are different claims, and only
the second is about isolation. The registry records this as an activation
obligation rather than leaving it to memory.

Nothing here is destructive. It reads state, and it presents credentials that are
expected to fail -- each after the project's own has been accepted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, secrets_contract

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


def test_two_projects_publish_distinct_routes_issuers_and_snapshots(
    project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """DEP-ISO-005, the structural half.

    Seven things that would each be a way for two API planes to share a
    boundary: the published REST and documentation routes, the authenticator
    roles, the documentation roles, the issuers, the audiences and the active key
    ids. Each is derived per project, so a shared value here is a derivation that
    read the wrong project's scope -- which is the shape of every cross-project
    mistake this suite exists to catch.

    The **project document digest** is asserted distinct and the **canonical
    snapshot digest** asserted identical, in the same test. That pair is the
    point: the reviewed surface is project-neutral and both projects must serve
    the same one, while the document each actually publishes carries its own host
    and must not be the other's.

    Goes red if: two projects render the same route, role, issuer or audience; a
    key is generated once and shared; or the two serve documents with the same
    digest, which would mean a route pointing at the other project's service.

    It would NOT go red for two projects whose *identifiers* differ while a
    credential still works across them, which is why the second test exists.
    """
    assert key(project_a) != key(project_b), "these are the same project"

    for pair in ("rest", "docs"):
        url_a = (project_a["routes"][pair] or {}).get("url")
        url_b = (project_b["routes"][pair] or {}).get("url")
        assert url_a and url_b, f"one of the projects publishes no {pair} route"
        assert url_a != url_b, f"both projects publish the {pair} route at {url_a}"

    for role in ("postgrest_authenticator", "api_documentation"):
        assert project_a["database"]["roles"][role] != project_b["database"]["roles"][role], (
            f"both projects use the same {role} role"
        )

    jwt_a, jwt_b = project_a["jwt"], project_b["jwt"]
    for member in ("issuer", "audience", "active_kid", "public_jwks_sha256"):
        assert jwt_a[member] != jwt_b[member], f"both projects share jwt.{member}"
    assert not set(jwt_a["verification_kids"]) & set(jwt_b["verification_kids"]), (
        "the two projects accept each other's signing keys"
    )

    api_a, api_b = project_a["api"], project_b["api"]
    assert api_a["canonical_openapi_sha256"] == api_b["canonical_openapi_sha256"], (
        "the two projects were deployed against different reviewed snapshots; the "
        "surface is project-neutral and a divergence here means one of them was "
        "approved separately"
    )
    assert api_a["project_openapi_sha256"] != api_b["project_openapi_sha256"], (
        "both projects publish byte-identical documents, so at least one of them "
        "records a host that is not its own"
    )


def test_one_projects_token_and_credential_are_refused_by_the_other(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    rest_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    mint_token: Callable[..., str],
    request_subject: Callable[[str], str],
    materialized_secret: Callable[[str, str, str], str],
    pg_login: Callable[..., tuple[int, str, str]],
    as_root: None,
) -> None:
    """DEP-ISO-005's cross-project clause, with its own node ID (D70).

    Three credentials presented across the boundary, and each **after** the
    target has accepted its own:

    **A token signed by A's key, sent to B's route.** Refused on the signature,
    because B verifies against its own JWKS. The token names B's *own*
    authenticated role, so a refusal cannot be attributed to a role that does not
    exist -- the mistake D70 records, one layer up.

    **A token signed by B's key naming A's role.** Refused on the membership: the
    signature verifies and the role does not exist at B, which is the other half
    and the one a shared key would hide.

    **A's authenticator password, against B's own authenticator role**, from a
    container on B's internal network. Both halves matter for the reason
    ``DEP-ISO-004`` records: against the foreign role it would fail because the
    role is absent, and from inside B's own cluster container it would succeed
    regardless of the password, because the image trusts loopback above its
    ``scram-sha-256`` line (D74).

    Goes red if: two projects are issued the same signing key or the same
    authenticator password -- which is what a provider path keyed on something
    other than the project produces; if B's PostgREST is configured with A's
    JWKS; or if either cluster stops checking a password at all.
    """
    del as_root
    target, other = project_b, project_a
    base = rest_base(target)
    target_role = target["database"]["roles"]["authenticated"]
    other_role = other["database"]["roles"]["authenticated"]
    subject = request_subject(key(target))

    own = mint_token(target, target_role, subject=subject)
    accepted = api_call(f"{base}/notes?limit=1", token=own)
    assert accepted.status == 200, (
        f"{key(target)} refused its own token ({accepted.status}); the refusals below "
        "would then be about a broken route rather than about isolation"
    )

    foreign_key = mint_token(other, target_role, subject=subject)
    assert foreign_key != own, "the two projects minted an identical token"
    refused = api_call(f"{base}/notes?limit=1", token=foreign_key)
    assert refused.status in (401, 403), (
        f"{key(target)} accepted a token signed by {key(other)}'s key ({refused.status}); "
        "the two projects share verification material"
    )

    foreign_role = mint_token(target, other_role, subject=subject)
    refused = api_call(f"{base}/notes?limit=1", token=foreign_role)
    assert refused.status in (401, 403, 500), (
        f"{key(target)} served a token naming {key(other)}'s role ({refused.status})"
    )

    network = target["edge"]["project_internal_network"]
    authenticator = target["database"]["roles"]["postgrest_authenticator"]

    # The authenticator's copy is written in `pgpass` format, so the file's
    # contents are not the password. Recovered with the product's own inverse
    # rather than by slicing the line here: `render_secret` and `recover_secret`
    # have a round-trip test, and a second parser would be the one that broke
    # silently the first time a password contained a colon.
    consumer = next(
        item
        for secret in secrets_contract.load_secret_contract(REPO_ROOT / "secrets.required.yaml")[
            "secrets"
        ]
        if secret["name"] == "postgrest_authenticator_password"
        for item in secret["consumers"]
    )
    own_password = secrets_contract.recover_secret(
        materialized_secret(key(target), "postgrest", "postgrest_authenticator_pgpass"), consumer
    )
    foreign_password = secrets_contract.recover_secret(
        materialized_secret(key(other), "postgrest", "postgrest_authenticator_pgpass"), consumer
    )
    assert own_password != foreign_password, (
        "both projects were issued the same authenticator credential; there is nothing "
        "to isolate and the refusal below would prove nothing"
    )

    status, _, stderr = pg_login(target, network, authenticator, own_password)
    assert status == 0, (
        f"{authenticator} could not authenticate with its own credential "
        f"({stderr.strip()}); the refusal below would be about a broken cluster"
    )

    status, _, stderr = pg_login(target, network, authenticator, foreign_password)
    assert status != 0, (
        f"{key(other)}'s authenticator credential authenticated as {authenticator} on "
        f"{key(target)}'s cluster"
    )
    assert "authentication failed" in stderr.lower(), (
        f"the login failed for an unexpected reason, so nothing was proved: {stderr.strip()}"
    )
