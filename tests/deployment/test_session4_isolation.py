"""Two projects, two transports each, nothing shared (DEP-ISO-004).

Replaces the Session 4 placeholder in ``tests/contract/test_future_deployment.py``.

**The credential clause carries its own node ID**, and that is the whole reason
this module is split from the identifier checks above it. D70: ``DEP-ISO-003``
claimed the same class of property for two runs behind six node IDs, and not one
of them presented a credential to anything. "The role names differ" and "one
project's credential is refused by the other's cluster" are different claims, and
only the second is about isolation.

Nothing here is destructive. It reads state, and it attempts one login that is
expected to fail.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.database,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]


def key(document: dict[str, Any]) -> str:
    return document["project"]["key"]


def test_two_projects_hold_distinct_transports_pools_and_user_lists(
    project_a, project_b, allocation_for, pool_console, pooler_container
) -> None:
    """DEP-ISO-004, the structural half.

    Four things that would each be a way for two projects to share a boundary:
    the allocated host ports, the pooler containers, the roles the poolers
    authenticate, and the databases they route to.

    Goes red if: a port range collision hands both projects one number; a second
    project's deploy reuses the first's pooler container; or a user list is
    written from a shared source and ends up naming both roles — which would
    make one project's application credential authenticate at the other's pool.

    It would NOT go red for two projects whose *names* differ while everything
    else is shared, which is why the credential test below exists as well.
    """
    allocation_a = allocation_for(key(project_a))
    allocation_b = allocation_for(key(project_b))

    ports_a = {allocation_a["pooled_port"], allocation_a["direct_port"]}
    ports_b = {allocation_b["pooled_port"], allocation_b["direct_port"]}
    assert len(ports_a) == 2 and len(ports_b) == 2
    assert not ports_a & ports_b, f"the two projects share host ports {sorted(ports_a & ports_b)}"

    assert allocation_a["instance_uuid"] != allocation_b["instance_uuid"]
    assert pooler_container(key(project_a)) != pooler_container(key(project_b))

    role_a = project_a["database"]["access_profiles"]["runtime_pooled"]["role"]
    role_b = project_b["database"]["access_profiles"]["runtime_pooled"]["role"]
    assert role_a != role_b

    # SHOW DATABASES is the pooler's own routing table. A pooler that listed the
    # other project's database would forward to a cluster it has no business
    # reaching, whatever its user list said.
    routes_a = pool_console(key(project_a), "SHOW DATABASES")
    assert project_b["database"]["name"] not in routes_a, (
        f"{key(project_a)}'s pooler routes to {project_b['database']['name']}"
    )

    # SHOW USERS is the user list, read out of the running daemon. The roles are
    # derived from the project key, so a pooler naming the other's role is a
    # user list assembled from the wrong project's environment.
    users_a = pool_console(key(project_a), "SHOW USERS")
    assert role_b not in users_a, f"{key(project_a)}'s pooler authenticates {role_b}"


def test_one_projects_runtime_credential_is_refused_by_the_others_cluster(
    project_a, project_b, materialized_secret, pg_login, as_root
) -> None:
    """DEP-ISO-004's credential clause, with its own node ID (D70).

    The foreign password is presented against the **target's own role**, from a
    container on the **target's internal network**. Both halves matter. Against
    the foreign role it would fail because the role does not exist, which proves
    nothing about credentials; and from inside the cluster's own container it
    would *succeed* regardless of the password, because the image's
    ``pg_hba.conf`` trusts loopback above its ``scram-sha-256`` line (D74).

    Goes red if: the two projects are issued the same application password —
    which is what a provider path keyed on something other than the project
    would produce — or if the target cluster stops checking the password at all.

    And the positive control runs first: the same role's **own** password is
    accepted. Without it, a cluster that refused every login would pass.
    """
    del as_root
    target = project_b
    network = target["edge"]["project_internal_network"]
    role = target["database"]["access_profiles"]["runtime_pooled"]["role"]

    own = materialized_secret(key(target), "pgbouncer", "app_runtime_password")
    foreign = materialized_secret(key(project_a), "pgbouncer", "app_runtime_password")
    assert own != foreign, (
        "both projects were issued the same application password; there is nothing "
        "to isolate and the refusal below would prove nothing"
    )

    status, _, stderr = pg_login(target, network, role, own)
    assert status == 0, (
        f"{role} could not authenticate with its own credential ({stderr.strip()}); "
        "the refusal below would then be about a broken cluster, not about isolation"
    )

    status, _, stderr = pg_login(target, network, role, foreign)
    assert status != 0, (
        f"{key(project_a)}'s application credential authenticated as {role} on "
        f"{key(target)}'s cluster"
    )
    assert "authentication failed" in stderr.lower(), (
        f"the login failed for an unexpected reason, so nothing was proved: {stderr.strip()}"
    )
