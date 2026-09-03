"""`IDN-*` live halves — the identity lifecycle against a real deployment.

The offline halves are in `tests/contract/`, and several already run against a
real cluster: `test_auth_endpoints.py` stands one up and applies every migration
through the product's own render path. **That is not the same thing as this
file.** Those prove the logic against a database this repository built; these
prove it against the deployment an operator is running, reached through the
published route, with the credentials that deployment holds.

The distinction is ADR 0065/0066's: *a proof that reaches the right end state by
a route the product does not take proves the end state is reachable, not that the
product reaches it.* A refresh that works against a fixture cluster on localhost
says nothing about whether the edge answers.

**Everything here uses the deployment suite's own fixtures.** The first draft did
not — it read `APG_ADMIN_PASSWORD_FILE` itself, re-derived the administrator's
username, and used `.strip()` on the password file where `conftest` deliberately
uses `.removesuffix("\\n")` because **a password may legitimately end in a
space**. That draft would have authenticated as something the operator did not
type and reported it as a broken deployment. Question 6, in the fixture I was
writing rather than in one I inherited: the suite already knew all of this.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = [pytest.mark.p0, pytest.mark.deployment]


def _auth(base: str) -> str:
    """The auth surface under a project's published application prefix.

    Derived from `app_base`, which reads `routes.app` and refuses a route that
    is not `ready` -- so a negative assertion here cannot pass against a
    hostname with no application router behind it (ADR 0158, ADR 0002).
    """
    return f"{base}/auth"


def _admin(base: str) -> str:
    return f"{base}/admin"


# ---------------------------------------------------------------------------
# IDN-SESSION-001
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_login_through_the_edge_carries_a_refresh_token(
    project_a: dict[str, Any],
    administrator_username: str,
    admin_password: str,
    app_login: Callable[..., Any],
) -> None:
    """The plane answers on its published route, not only in a fixture.

    Before Session 15 a login response carried an access token and nothing else
    (D812), so this could not have passed against any earlier release -- which
    is what makes it a proof of THIS one rather than of the endpoint's continued
    existence.
    """
    response = app_login(project_a, administrator_username, admin_password)
    assert response.status == 200, f"{response.status} {response.body}"
    body = json.loads(response.body)
    assert body.get("refresh_token"), (
        "the deployed login carries no refresh token, so this release's session plane "
        "is not the one answering"
    )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_a_client_renews_through_the_edge_without_the_password(
    project_a: dict[str, Any],
    administrator_username: str,
    admin_password: str,
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """IDN-SESSION-001 against the deployment. D813 is why it is a security proof.

    A token lives at most 930 seconds and nothing renewed it, so a client
    staying logged in had to keep the PASSWORD. This holds the refresh token
    ALONE, obtains an access token through the published route, and reaches an
    authenticated endpoint with it.

    **The CONTROL is that the renewed token differs from the first.** Without it
    an implementation that echoed the presented value back would satisfy every
    other assertion here.
    """
    base = app_base(project_a)
    opened = json.loads(app_login(project_a, administrator_username, admin_password).body)
    held = opened["refresh_token"]

    renewed = api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": held})
    assert renewed.status == 200, f"the deployed refresh route refused: {renewed.body}"
    body = json.loads(renewed.body)
    assert body["access_token"] != opened["access_token"], "refresh echoed the token back"
    assert body["refresh_token"] != held, "the refresh token did not rotate"

    reached = api_call(f"{_auth(base)}/me", token=body["access_token"])
    assert reached.status == 200, f"the renewed token does not authenticate: {reached.body}"


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_a_replayed_refresh_token_ends_the_session_on_the_deployment(
    project_a: dict[str, Any],
    administrator_username: str,
    admin_password: str,
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """Reuse detection through the edge, with the successor as the control.

    Asserting only that the replay is refused would pass against an
    implementation that refused the spent value and left the live successor
    working -- which is a thief still holding a session.
    """
    base = app_base(project_a)
    opened = json.loads(app_login(project_a, administrator_username, admin_password).body)
    parent = opened["refresh_token"]

    rotated = api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": parent})
    assert rotated.status == 200, rotated.body
    successor = json.loads(rotated.body)["refresh_token"]

    replay = api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": parent})
    assert replay.status == 401, f"a replayed token was accepted: {replay.body}"

    after = api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": successor})
    assert after.status == 401, (
        "the live successor still works after a replay, so the family was not revoked "
        "and a thief who replayed once would still hold a session"
    )


# ---------------------------------------------------------------------------
# IDN-SESSION-002
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_sessions_are_listable_and_terminable_on_the_deployment(
    project_a: dict[str, Any],
    administrator_username: str,
    admin_password: str,
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """IDN-SESSION-002 live, and the second half is what makes it real.

    A listing that named sessions and could not end them would be a report. What
    is asserted is that a terminated session's refresh token stops working --
    ending a session has to reach the credential, not only a row somebody reads.
    """
    base = app_base(project_a)
    first = json.loads(app_login(project_a, administrator_username, admin_password).body)
    second = json.loads(app_login(project_a, administrator_username, admin_password).body)

    listed = api_call(f"{_auth(base)}/sessions", token=second["access_token"])
    assert listed.status == 200, listed.body
    sessions = json.loads(listed.body)
    assert len(sessions) >= 2, f"expected at least two sessions, got {sessions}"

    # No caller-supplied string is stored (D829), so a listing cannot name a
    # device. Asserted here too, because the deployment is where a well-meaning
    # later change would add one.
    assert set(sessions[0]) == {
        "session_id",
        "created_at",
        "last_used_at",
        "revoked_at",
        "revoked_reason",
    }, f"the deployed listing carries an unexpected member: {sorted(sessions[0])}"

    live = [row for row in sessions if row["revoked_at"] is None]
    assert live, "no live session to end"
    ended = api_call(
        f"{_auth(base)}/sessions/{live[0]['session_id']}",
        method="DELETE",
        token=second["access_token"],
    )
    assert ended.status == 204, f"ending a session answered {ended.status}: {ended.body}"

    outcomes = sorted(
        api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": token}).status
        for token in (first["refresh_token"], second["refresh_token"])
    )
    assert outcomes == [200, 401], (
        f"ending one session left {outcomes}; exactly one refresh token should survive"
    )


# ---------------------------------------------------------------------------
# IDN-AGENT-001
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_a_revoked_agent_is_not_reinstated_by_flipping_the_flag(
    project_a: dict[str, Any],
    admin_session: Any,
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """IDN-AGENT-001 and D503, closed against the deployment (ADR 0172).

    Before this release the transition answered 200 and the ORIGINAL secret
    authenticated again -- measured 200/401/200. Here it is refused, the agent
    stays revoked, and rotation is the way back with the old secret dead.
    """
    base = app_base(project_a)
    created = api_call(
        f"{_admin(base)}/agents",
        method="POST",
        token=admin_session.token,
        body={
            "name": f"session15-live-{os.getpid()}",
            "description": "IDN-AGENT-001 live half",
            "role": "agent_reader",
            "scopes": ["notes:read"],
        },
    )
    assert created.status == 201, created.body
    agent = json.loads(created.body)
    agent_id, secret = agent["agent_id"], agent["secret"]

    def exchange(value: str) -> int:
        return api_call(
            f"{_auth(base)}/agent-token",
            method="POST",
            body={"agent_id": agent_id, "secret": value},
        ).status

    assert exchange(secret) == 200, "CONTROL failed: the new agent never worked"

    revoked = api_call(
        f"{_admin(base)}/agents/{agent_id}",
        method="PATCH",
        token=admin_session.token,
        body={"status": "revoked"},
    )
    assert revoked.status == 200, revoked.body
    assert exchange(secret) == 401

    refused = api_call(
        f"{_admin(base)}/agents/{agent_id}",
        method="PATCH",
        token=admin_session.token,
        body={"status": "active"},
    )
    assert refused.status == 422, (
        f"the deployment still allows un-revoking: {refused.status} {refused.body}"
    )
    assert "rotating its secret" in refused.body, (
        "the refusal does not name the operation that works"
    )
    assert exchange(secret) == 401, "the refused transition still reinstated the agent"

    rotated = api_call(
        f"{_admin(base)}/agents/{agent_id}/rotate-secret",
        method="POST",
        token=admin_session.token,
    )
    assert rotated.status == 200, rotated.body
    assert exchange(json.loads(rotated.body)["secret"]) == 200, (
        "rotation did not clear the revocation, so an agent revoked by mistake is dead"
    )
    assert exchange(secret) == 401, (
        "the pre-revocation secret works again, so reinstatement restored the credential "
        "the revocation was the response to"
    )


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_deployment_publishes_an_expiry_for_every_agent_credential(
    project_a: dict[str, Any],
    admin_session: Any,
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """The half an operator reads (ADR 0172).

    An expiry nobody can see is an outage with a countdown. A credential issued
    before this release carries `null` and does not expire, which is the
    migration's own decision -- so this asserts the FIELD is published, not that
    every value is set.
    """
    listed = api_call(f"{_admin(base := app_base(project_a))}/agents", token=admin_session.token)
    del base
    assert listed.status == 200, listed.body
    agents = json.loads(listed.body)["agents"]
    assert agents, "no agents on the deployment, so this asserted nothing"
    for agent in agents:
        assert "secret_expires_at" in agent, (
            f"{agent['agent_id']} publishes no expiry, so an operator cannot see one coming"
        )


# ---------------------------------------------------------------------------
# IDN-RESET-001
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_a_reset_on_the_deployment_learns_no_password_and_ends_the_sessions(
    project_a: dict[str, Any],
    admin_session: Any,
    app_login: Callable[..., Any],
    api_call: Callable[..., Any],
    app_base: Callable[[dict[str, Any]], str],
) -> None:
    """IDN-RESET-001 live: the negative proof, and the half D845 added.

    A subject logs in and holds both an access token and a refresh chain. After
    the reset **both are refused** -- the access token because
    `credential_version` moved, the chain because the reset ends every session
    (ADR 0173). Asserting only the first would pass against a reset that left a
    live way in.

    The administrator sees a reset token and never the password: the subject
    chooses it here.
    """
    base = app_base(project_a)
    username = f"reset-live-{os.getpid()}"
    original = "a-correct-horse-battery-staple-15"
    chosen = "another-correct-horse-staple-15"

    created = api_call(
        f"{_admin(base)}/users",
        method="POST",
        token=admin_session.token,
        body={
            "username": username,
            "display_name": "IDN-RESET-001 live half",
            "role": "authenticated",
            "scopes": ["notes:read"],
            "password": original,
        },
    )
    assert created.status == 201, created.body
    user_id = json.loads(created.body)["user_id"]

    opened = app_login(project_a, username, original)
    assert opened.status == 200, opened.body
    session = json.loads(opened.body)
    access, refresh = session["access_token"], session["refresh_token"]

    assert api_call(f"{_auth(base)}/me", token=access).status == 200, (
        "CONTROL failed: the subject's token never worked"
    )

    issued = api_call(
        f"{_admin(base)}/users/{user_id}/reset-password",
        method="POST",
        token=admin_session.token,
    )
    assert issued.status == 201, issued.body
    assert "password" not in issued.body, "the reset response carries a password"
    reset_token = json.loads(issued.body)["reset_token"]

    spent = api_call(
        f"{_auth(base)}/reset-password",
        method="POST",
        body={"reset_token": reset_token, "password": chosen},
    )
    assert spent.status == 200, spent.body

    assert api_call(f"{_auth(base)}/me", token=access).status == 401, (
        "an access token issued before the reset still works on the deployment"
    )
    assert (
        api_call(f"{_auth(base)}/refresh", method="POST", body={"refresh_token": refresh}).status
        == 401
    ), (
        "a refresh chain obtained with the old password survived the reset, so a session "
        "outlives the credential it was obtained with (D845)"
    )
    assert app_login(project_a, username, chosen).status == 200, (
        "the subject cannot log in with the password they chose"
    )


# ---------------------------------------------------------------------------
# IDN-ROT-001
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS")
def test_the_rotation_surface_describes_this_deployments_generation(
    as_root: None, project_a: dict[str, Any]
) -> None:
    """IDN-ROT-001's live half: the plan is about THIS deployment's files.

    The offline half asserts the surface refuses what it cannot rotate, which is
    a property of the contract and would hold against a deployment that had none
    of these files. **This checks the plan against what is on disk**: every
    secret the surface says replacement would reach has a materialized file in
    the active generation. A refusal about a file that does not exist would be a
    refusal about nothing.
    """
    del as_root
    from agentic_postgres import REPO_ROOT, rotation
    from agentic_postgres.secret_generation import SECRET_ROOT
    from agentic_postgres.secrets_contract import consumer_directory, load_secret_contract

    contract = load_secret_contract(REPO_ROOT / "secrets.required.yaml")
    session = int(project_a["deployed_through_session"])
    generation = (
        SECRET_ROOT
        / project_a["project"]["key"]
        / "generations"
        / project_a["secrets"]["generation_id"]
    )
    assert generation.is_dir(), f"no generation at {generation}"

    planned = {v.name for v in rotation.plan_all(contract, session)}
    assert planned, "the surface plans nothing for this deployment's session"

    missing: list[str] = []
    for secret in contract["secrets"]:
        if secret["name"] not in planned:
            continue
        for consumer in secret["consumers"]:
            path = Path(generation) / consumer_directory(consumer) / consumer["target_file"]
            if not path.is_file():
                missing.append(f"{secret['name']} -> {path}")
    assert not missing, (
        "the rotation surface names secrets whose consumer files do not exist in the "
        f"deployed generation, so the plan describes files nothing wrote: {missing}"
    )
