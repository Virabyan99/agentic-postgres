"""One project's identity plane is refused by the other (DEP-ISO-006).

`DEP-ISO-002` is about containers and networks, `DEP-ISO-003` about databases,
`DEP-ISO-004` about transports and `DEP-ISO-005` about the REST surface. This is
the identity plane, and it needs its own ID for the reason ADR 0089 records: a
claim built over `DEP-ISO-003` would resolve to Session 3 and turn three earlier
sessions' evidence red.

**Isolation here has two halves and only one of them is a request.** The first
is that project A's token is refused by project B -- measurable, and the obvious
proof. The second is that there is nothing for the two to share: separate keys,
separate issuers, separate audiences, separate advisory-lock keys, separate
credentials. The first half can pass by accident (B's route might be down); the
second cannot, and it is what makes the first half mean something.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.security,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]


def test_the_two_projects_share_no_identity_material(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
) -> None:
    """The half that cannot pass by accident.

    Every value that would let one project's token be honoured by the other is
    compared and must differ: the key identifiers, the issuer, the audience, the
    published JWKS digest, and the derived role names the tokens name.

    The equality direction is asserted too -- that both documents are describing
    a *deployed* project of the same schema version -- because two documents
    that differ in everything would also satisfy "shares nothing", including two
    readings of the same broken deploy.

    Goes red if: a project is deployed with another's issuer or audience; the
    key derivation stops being per-project; or two projects converge on one role
    name, which would make PostgREST's role switching cross the boundary.
    """
    assert project_a["project"]["key"] != project_b["project"]["key"], (
        "both documents describe the same project, so nothing here is a comparison"
    )
    assert project_a["schema_version"] == project_b["schema_version"], (
        f"the two projects are at schema versions {project_a['schema_version']} and "
        f"{project_b['schema_version']}; one of them has not been redeployed, and every "
        "difference below could be a version difference rather than isolation"
    )

    a_jwt, b_jwt = project_a["jwt"], project_b["jwt"]
    for field in ("issuer", "audience", "active_kid", "public_jwks_sha256"):
        assert a_jwt[field] != b_jwt[field], (
            f"both projects publish the same jwt.{field} ({a_jwt[field]!r}). A token "
            "minted for one would be honoured by the other"
        )

    shared_kids = set(a_jwt["verification_kids"]) & set(b_jwt["verification_kids"])
    assert not shared_kids, (
        f"the two projects publish {len(shared_kids)} verification key(s) in common: "
        f"{sorted(shared_kids)}. Either they share a signing key or two different keys "
        "have produced the same RFC 7638 thumbprint"
    )

    a_roles = set(project_a["database"]["roles"].values())
    b_roles = set(project_b["database"]["roles"].values())
    assert not (a_roles & b_roles), (
        f"the two projects share role names: {sorted(a_roles & b_roles)}. A token naming "
        "one would switch to the same role in either cluster"
    )


def test_project_bs_route_refuses_project_as_administrator(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    admin_session: Any,
) -> None:
    """The request half, with the control that makes a 401 meaningful.

    A cross-project 401 proves nothing on its own: an unreachable route, an
    unpublished one and a correctly refusing one are indistinguishable from a
    status code. So project B's own surface is exercised first -- it must answer
    an *unauthenticated* request with 401 and a challenge, which establishes that
    something is listening and rejecting -- and only then is A's token presented.

    Goes red if: the two projects converge on one issuer or key set; B's
    verifier starts accepting any signature; or B's application route is
    published without a verifier at all, which would answer 200.
    """
    b_base = app_base(project_b)

    unauthenticated = api_call(f"{b_base}/auth/me")
    assert unauthenticated.status == 401, (
        f"project B's /auth/me answered {unauthenticated.status} without a token. Until "
        "this is a 401 the cross-project refusal below cannot be attributed to the "
        "boundary rather than to an absent route"
    )

    crossed = api_call(f"{b_base}/auth/me", token=admin_session.token)
    assert crossed.status == 401, (
        f"project B accepted project A's administrator token ({crossed.status}: "
        f"{crossed.body[:200]!r}). The identity planes are not separate"
    )

    # And the reverse reading: A's own route accepts it. Without this the test
    # is satisfied by a token that is simply invalid everywhere.
    home = api_call(f"{app_base(project_a)}/auth/me", token=admin_session.token)
    assert home.status == 200, (
        f"project A refused its own administrator token ({home.status}); the refusal "
        "above is a fact about the token, not about the boundary"
    )


def test_project_bs_key_set_does_not_verify_project_as_tokens(
    project_a: dict[str, Any],
    project_b: dict[str, Any],
    app_base: Callable[[dict[str, Any]], str],
    api_call: Callable[..., Any],
    admin_session: Any,
) -> None:
    """The same boundary read from the published key sets rather than from a status.

    A 401 says the token was refused. It does not say *why*, and the answer
    matters: refused because the signature does not verify is isolation, and
    refused because the subject is unknown is a coincidence that would evaporate
    the moment the two projects happened to hold a subject with the same name.

    So this asserts the mechanism directly -- the `kid` A's token names is absent
    from everything B publishes.
    """
    header = admin_session.token.split(".")[0]
    kid = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))["kid"]

    assert kid in project_a["jwt"]["verification_kids"], (
        f"the token names kid {kid!r}, which project A does not publish. Whatever the "
        "next assertion finds would be a fact about a token nobody can verify"
    )

    published = api_call(f"{app_base(project_b)}/auth/jwks.json")
    assert published.status == 200, f"project B's JWKS answered {published.status}"
    served = [key["kid"] for key in json.loads(published.body)["keys"]]

    assert kid not in served, (
        f"project A's token names kid {kid!r}, which project B publishes. B can verify "
        "A's signatures, so the refusal is about the subject rather than about the key"
    )
    assert served == project_b["jwt"]["verification_kids"], (
        f"project B serves {served} where its document records "
        f"{project_b['jwt']['verification_kids']}; the two readings disagree, so neither "
        "is a reliable statement about what B will verify"
    )
