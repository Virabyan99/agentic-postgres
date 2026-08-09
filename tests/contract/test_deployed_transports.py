"""The writer the transport blocks did not have (D112).

Found by deploying Project A through session 4 in Run 9 and reading the document
back: every profile said `unavailable` with a null reference, on a host whose
pooler was healthy and whose secrets were materialized. The render hard-codes
those values because a render knows no port; `build_deployed_document` carried
the rendered `database` block through verbatim; and three readers depended on a
field nothing set.

These tests are what would have caught it offline. The one that matters most is
the reservation case: a document that reported `available` off a *reserved*
allocation would be claiming an endpoint answers because something once intended
it to — and §4.1 puts the off-host scan before the promotion that makes an
allocation active, so it would also be making the claim ahead of the check that
guards it.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentic_postgres import access_policy, deployed_output

pytestmark = [pytest.mark.contract, pytest.mark.p0]

LOOPBACK = "127.0.0.1"
ROLE = "apg_alpha_dev_app_runtime"
MIGRATION_ROLE = "apg_alpha_dev_migration_user"


def rendered() -> dict[str, Any]:
    unavailable = {
        "status": "unavailable",
        "available_from_session": 4,
        "host": None,
        "port": None,
        "url": None,
        "password_secret_ref": None,
    }
    return {
        "database": {
            "name": "alpha_dev",
            "pooled": dict(unavailable),
            "direct": dict(unavailable),
            "access_profiles": {
                "runtime_pooled": {
                    "status": "unavailable",
                    "available_from_session": 4,
                    "transport": "pooled",
                    "role": ROLE,
                    "password_secret_ref": None,
                },
                "runtime_direct": {
                    "status": "unavailable",
                    "available_from_session": 4,
                    "transport": "direct",
                    "role": ROLE,
                    "password_secret_ref": None,
                },
                "migration_direct": {
                    "status": "unavailable",
                    "available_from_session": 4,
                    "transport": "direct",
                    "role": MIGRATION_ROLE,
                    "password_secret_ref": None,
                },
            },
        }
    }


def allocation(state: str = "active") -> dict[str, Any]:
    return {
        "instance_uuid": "90db04ed-c8c0-4fab-862b-e4e34e4ad0fa",
        "project_key": "alpha-dev",
        "pooled_port": 15432,
        "direct_port": 15433,
        "state": state,
    }


def observe(**kwargs: Any) -> dict[str, Any]:
    return deployed_output.observe_transports(
        rendered=rendered(), loopback_address=LOOPBACK, **kwargs
    )


@pytest.mark.parametrize("state", ["reserved", "released"])
def test_only_an_active_allocation_makes_a_transport_available(state: str) -> None:
    """`reserved` is two ports set aside and nothing connected to either.

    Goes red if availability is keyed on an allocation existing rather than on
    it having been verified — which would publish `available` before the
    off-host scan §4.1 puts in front of the promotion.
    """
    result = observe(allocation=allocation(state))
    assert result["pooled"]["status"] == "unavailable"
    assert result["direct"]["status"] == "unavailable"
    assert result["pooled"]["port"] is None
    for profile in result["access_profiles"].values():
        assert profile["status"] == "unavailable"
        assert profile["password_secret_ref"] is None


def test_no_allocation_leaves_the_rendered_values_alone() -> None:
    """A session-2 or session-3 deployment has no transport to describe."""
    result = observe(allocation=None)
    assert result["pooled"] == rendered()["database"]["pooled"]
    assert result["access_profiles"] == rendered()["database"]["access_profiles"]


def test_an_active_allocation_publishes_both_transports() -> None:
    """The failure this whole module exists for.

    Goes red if the deploy stops reading the registry, or reads it and does not
    write the result into the document — which is the state Run 9 found on a
    host where everything else was correct.
    """
    result = observe(allocation=allocation())

    assert (result["pooled"]["status"], result["pooled"]["port"]) == ("available", 15432)
    assert (result["direct"]["status"], result["direct"]["port"]) == ("available", 15433)
    assert result["pooled"]["host"] == result["direct"]["host"] == LOOPBACK

    for profile_name, profile in result["access_profiles"].items():
        assert profile["status"] == "available"
        assert profile["password_secret_ref"] == access_policy.PROFILE_SECRETS[profile_name][0]

    # The role and transport are derivations and must survive untouched: the
    # migration profile keeps its own role, and publishing availability is not
    # an opportunity to rewrite who a profile connects as.
    assert result["access_profiles"]["migration_direct"]["role"] == MIGRATION_ROLE
    assert result["access_profiles"]["runtime_pooled"]["transport"] == "pooled"


def test_the_published_url_cannot_carry_a_password() -> None:
    """The same rule `postgresUrl` states in the schema, checked at the writer.

    A URL is the one field here assembled from parts, so it is the one that
    could acquire a credential by someone helpfully interpolating one.
    """
    result = observe(allocation=allocation())
    for transport in ("pooled", "direct"):
        url = result[transport]["url"]
        userinfo = url.split("//", 1)[1].split("@", 1)[0]
        assert ":" not in userinfo, f"{transport} url carries a password: {url}"
        assert url.startswith(f"postgresql://{ROLE}@{LOOPBACK}:")


def test_the_document_validates_once_the_transports_are_published() -> None:
    """The schema binds the available case as tightly as the unavailable one.

    Version 4 made that true; before it, a document could claim `available` with
    every field null. This asserts the writer produces something that survives
    the constraint rather than something that merely looks right.
    """
    result = observe(allocation=allocation())
    for transport in ("pooled", "direct"):
        block = result[transport]
        # Every member the schema's `else` branch requires of an available
        # endpoint, none of them null. The version-3 schema bound only the
        # unavailable case, so a document could say `available` and tell you
        # nothing; these are the four fields that closed it.
        assert isinstance(block["port"], int)
        assert isinstance(block["host"], str) and block["host"]
        assert isinstance(block["url"], str) and block["url"]
        assert isinstance(block["password_secret_ref"], str) and block["password_secret_ref"]


def test_the_secret_reference_is_the_one_the_broker_will_look_for() -> None:
    """Two definitions of one fact, asserted to agree.

    The broker compares the document's recorded reference against its own
    mapping and refuses on disagreement rather than choosing. A writer that
    invented its own names would produce documents the release will not serve.
    """
    assert deployed_output.SECRET_FOR_PROFILE == {
        name: secret for name, (secret, _) in access_policy.PROFILE_SECRETS.items()
    }
