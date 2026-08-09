"""The decision behind a handed-out credential (ADR 0043).

Everything here runs with no root, no host and no cluster, which is the reason
the decision was pulled out of the broker in the first place. The cases that
matter are the ones nobody can arrange on a live machine: the duplicate grant
where one of two lines is dead, the profile a caller was never meant to have
arriving through a fallback, the policy that validates and permits everything.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, access_policy
from agentic_postgres.access_policy import PolicyError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

OPERATOR = "op"
PROJECT = "agentic-alpha-dev"
OTHER_PROJECT = "agentic-beta-dev"


def policy(*grants: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "grants": list(grants)}


def grant(user: str = OPERATOR, project: str = PROJECT, *profiles: str) -> dict[str, Any]:
    return {
        "unix_user": user,
        "project_key": project,
        "profiles": list(profiles) or ["runtime_direct"],
    }


# ---------------------------------------------------------------------------
# The shape of the document
# ---------------------------------------------------------------------------


def test_an_empty_policy_is_a_valid_policy() -> None:
    """A host that delegates nothing has to be expressible.

    Otherwise the only way to say it is to delete the file, and a missing file
    means state was lost -- which needs a different response from a deliberate
    decision to grant nobody anything.
    """
    assert access_policy.validate(access_policy.empty_policy())["grants"] == []


@pytest.mark.parametrize(
    ("document", "because"),
    [
        ({"grants": []}, "no schema_version"),
        ({"schema_version": 2, "grants": []}, "an unknown schema version"),
        ({"schema_version": 1}, "no grants member"),
        ({"schema_version": 1, "grants": [], "extra": 1}, "an unknown property"),
        ({"schema_version": 1, "grants": [{"unix_user": "op"}]}, "an incomplete grant"),
    ],
)
def test_a_malformed_policy_is_refused(document: dict[str, Any], because: str) -> None:
    with pytest.raises(PolicyError):
        access_policy.validate(document)
    assert because  # the parameter names why, and is read in the failure output


@pytest.mark.parametrize("wildcard", ["*", "all", "any-project"])
def test_a_wildcard_project_key_is_not_a_project_key(wildcard: str) -> None:
    """There is deliberately no wildcard anywhere in this document.

    ``*`` and ``all`` fail the pattern outright. ``any-project`` is the
    interesting one: it is a perfectly valid project key, so it is accepted --
    and it grants access to a project called ``any-project`` and to nothing else.
    That is the whole point. A grant cannot be written that covers a project
    deployed next month by someone else.
    """
    document = policy(grant(OPERATOR, wildcard, "runtime_direct"))
    if wildcard == "any-project":
        assert access_policy.validate(document)
        assert not access_policy.permits(
            document, unix_user=OPERATOR, project_key=PROJECT, profile="runtime_direct"
        )
    else:
        with pytest.raises(PolicyError):
            access_policy.validate(document)


def test_an_unknown_profile_name_is_refused_by_the_schema() -> None:
    """The profile name selects which secret is read. A free-form string here
    would be an arbitrary secret name arriving from a file."""
    with pytest.raises(PolicyError):
        access_policy.validate(policy(grant(OPERATOR, PROJECT, "superuser_direct")))


def test_two_grants_for_one_account_and_project_are_refused() -> None:
    """``uniqueItems`` compares whole objects, so the schema accepts this.

    Two grants differing only in their profile list both validate, and then one
    of them silently wins. Merging them would be worse: it would grant the union
    of two lines an operator wrote as alternatives.
    """
    document = policy(
        grant(OPERATOR, PROJECT, "runtime_direct"),
        grant(OPERATOR, PROJECT, "migration_direct"),
    )
    # Stated explicitly: the schema is happy, and that is why this module exists.
    from agentic_postgres import config

    config.validate_against_schema(document, access_policy.SCHEMA_NAME)

    with pytest.raises(PolicyError, match="appears twice"):
        access_policy.validate(document)


def test_the_same_account_may_hold_grants_for_two_projects() -> None:
    document = access_policy.validate(
        policy(
            grant(OPERATOR, PROJECT, "runtime_direct"),
            grant(OPERATOR, OTHER_PROJECT, "runtime_pooled"),
        )
    )
    assert access_policy.permits(
        document, unix_user=OPERATOR, project_key=PROJECT, profile="runtime_direct"
    )
    assert not access_policy.permits(
        document, unix_user=OPERATOR, project_key=OTHER_PROJECT, profile="runtime_direct"
    )


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "project", "profile", "expected"),
    [
        (OPERATOR, PROJECT, "runtime_direct", True),
        (OPERATOR, PROJECT, "runtime_pooled", True),
        (OPERATOR, PROJECT, "migration_direct", False),
        ("someone-else", PROJECT, "runtime_direct", False),
        (OPERATOR, OTHER_PROJECT, "runtime_direct", False),
        (OPERATOR, PROJECT, "not_a_profile", False),
    ],
)
def test_permits_answers_only_what_was_written_down(
    user: str, project: str, profile: str, expected: bool
) -> None:
    document = access_policy.validate(
        policy(grant(OPERATOR, PROJECT, "runtime_direct", "runtime_pooled"))
    )
    assert (
        access_policy.permits(document, unix_user=user, project_key=project, profile=profile)
        is expected
    )


def test_migration_authority_is_never_implied_by_direct_access() -> None:
    """The two direct profiles share a transport and nothing else.

    A helper that reasoned "they asked for direct, and migration_direct is
    direct" would substitute the schema owner's credential for the
    application's. The transport is a property of the endpoint; the authority is
    a property of the role.
    """
    document = access_policy.validate(policy(grant(OPERATOR, PROJECT, "runtime_direct")))
    assert access_policy.transport_for("runtime_direct") == "direct"
    assert access_policy.transport_for("migration_direct") == "direct"
    assert not access_policy.permits(
        document, unix_user=OPERATOR, project_key=PROJECT, profile="migration_direct"
    )


def test_an_unknown_profile_refuses_rather_than_raising() -> None:
    """The broker validates the name as input first. If that check is ever
    removed, this must still be a refusal: a traceback and a refusal are the
    same answer only when somebody is reading."""
    document = access_policy.validate(access_policy.empty_policy())
    assert (
        access_policy.permits(
            document, unix_user=OPERATOR, project_key=PROJECT, profile="../../etc/shadow"
        )
        is False
    )


def test_the_default_profile_is_not_a_privileged_one() -> None:
    """What a caller gets by not choosing has to be the least of what exists."""
    assert access_policy.DEFAULT_PROFILE in access_policy.PROFILES
    assert access_policy.DEFAULT_PROFILE not in access_policy.PRIVILEGED_PROFILES
    assert access_policy.PRIVILEGED_PROFILES <= set(access_policy.PROFILES)


# ---------------------------------------------------------------------------
# The mappings, checked against the files that also hold them
# ---------------------------------------------------------------------------


def test_every_profile_maps_to_a_secret_that_is_actually_declared() -> None:
    """The broker reads a file whose name comes from PROFILE_SECRETS.

    A name that no longer matches ``secrets.required.yaml`` is a broker that
    fails with "not materialized" for a credential that exists under another
    name -- and the operator's next move is to materialize secrets again, which
    changes nothing. The consumer directory is checked too, because it is a path
    component: the copy under ``pgbouncer/`` and the copy under ``dbmate/`` are
    different files with different owners, and that separation is the point.
    """
    contract = yaml.safe_load((REPO_ROOT / "secrets.required.yaml").read_text(encoding="utf-8"))
    declared = {
        secret["name"]: {consumer["service"] for consumer in secret["consumers"]}
        for secret in contract["secrets"]
    }

    for profile, (secret_name, consumer) in access_policy.PROFILE_SECRETS.items():
        assert secret_name in declared, f"{profile} maps to undeclared secret {secret_name}"
        assert consumer in declared[secret_name], (
            f"{profile} reads {secret_name} from {consumer}/, which is not a declared "
            f"consumer of it (declared: {sorted(declared[secret_name])})"
        )


def test_the_transport_map_agrees_with_the_output_schema() -> None:
    """The schema fixes each profile's transport with a ``const``.

    Two definitions of one fact is one fact that can disagree. This asserts they
    do not, rather than trusting that the module imported the right one.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    profiles = schema["$defs"]["accessProfiles"]["properties"]
    for profile in access_policy.PROFILES:
        const = profiles[profile]["allOf"][1]["properties"]["transport"]["const"]
        assert access_policy.transport_for(profile) == const


def test_the_policy_schema_and_the_module_name_the_same_profiles() -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "database-access-policy.schema.json").read_text(encoding="utf-8")
    )
    assert set(schema["$defs"]["accessProfileName"]["enum"]) == set(access_policy.PROFILES)
    assert set(access_policy.PROFILE_SECRETS) == set(access_policy.PROFILES)


def test_the_published_policy_path_is_host_state_not_project_state() -> None:
    """Which accounts may reach which projects is a fact about the machine.

    Under a project's directory it would be deletable by a redeploy of that
    project, and unreachable when deciding about a project that does not exist --
    which is exactly when the broker consults it.
    """
    assert access_policy.POLICY_PATH == "/etc/agentic-postgres/database-access-policy.json"
