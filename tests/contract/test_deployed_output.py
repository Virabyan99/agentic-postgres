"""The deployed document: an observation, held to a different standard.

Built from the *real* rendered fixture rather than a hand-made dictionary. A
hand-built input drifts away from what `render-config` actually produces, and
then this file proves something about a document nobody has.

The interesting property is the one the schema enforced against me while this
module was being written: rendered documents report `routes.health.status` as
`planned`, and deployed documents accept only `ready` or `unavailable`. Carrying
the field across looked obviously right — same name, same object, already
validated — and would have published "the health endpoint is fine" on the
strength of a manifest having once said it would be. A render-time claim and a
measurement are different facts wearing one field name.
"""

from __future__ import annotations

import ast
import contextlib
import http.server
import json
import threading
from pathlib import Path

import pytest
import yaml

from agentic_postgres import (
    REPO_ROOT,
    config,
    deployed_output,
    edge_credentials,
    jwt_keys,
    openapi_normalize,
    secrets_contract,
)
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

KEY = "fixture-alpha-dev"
COMMIT = "a" * 40
INSTANCE_UUID = "01927d3f-1a2b-7c4d-8e5f-6a7b8c9d0e1f"

#: A 43-character base64url string, which is what an RFC 7638 thumbprint is.
KID = "b" * 43


@pytest.fixture(scope="module")
def rendered() -> dict:
    path = REPO_ROOT / ".generated" / KEY / "outputs.json"
    if not path.exists():
        pytest.skip("fixtures are not rendered in this working tree")
    return json.loads(path.read_text(encoding="utf-8"))


OBSERVED = {
    "host": {
        "id": "apg-vps-01",
        "os_release": "26.04",
        "public_ipv4": "203.0.113.10",
        "public_ipv6": None,
    },
    "edge": {
        "stack_name": "apg-edge",
        "control_network": "apg-edge_control",
        "egress_network": "apg-edge_egress",
        "project_network_attached": True,
    },
    "tls": {
        "status": "issued",
        "acme_environment": "staging",
        "resolver": "letsencrypt-staging",
        "certificate_sha256": "c" * 64,
        "not_before": "2026-08-05T00:00:00Z",
        "not_after": "2026-11-03T00:00:00Z",
    },
    "bootstrap": {
        "status": "complete",
        "state_path": f"/etc/agentic-postgres/projects/{KEY}/bootstrap-state.json",
        "infisical_project_id": "5fffcd38-9af6-4f9d-bef9-c6eefc5e696f",
        "runtime_identity_id": "3302b5a4-7288-424f-bcd3-6cd158617827",
    },
    "secrets": {
        "status": "ready",
        "generation_id": "k7f2p9qd",
        "generation_manifest": (
            f"/var/lib/agentic-postgres/secrets/{KEY}/generations/k7f2p9qd/manifest.json"
        ),
        "required_names": ["session2_sentinel"],
        "fresh": True,
        "materialized_at": "2026-08-05T18:00:00Z",
    },
    "runtime": {
        "release_path": f"/opt/agentic-postgres/releases/{COMMIT}",
        "state_directory": f"/etc/agentic-postgres/projects/{KEY}",
        "compose_model_sha256": "d" * 64,
    },
    # A real Session 3 reading of a cluster. The default here is a measurement
    # rather than `NOT_OBSERVED`, so that the tests below exercise the branch a
    # deployed host is actually in; the not-observed case gets its own test.
    "database_observed": {
        "status": "observed",
        "server_version": "18.4",
        "extensions": {"vector": "0.8.6", "plpgsql": "1.0"},
        "memory": {"anon_mb": 62, "shmem_mb": 140, "file_mb": 410},
        "instance_uuid": INSTANCE_UUID,
    },
}

#: A published API surface, version 5. Written out rather than taken from a
#: constant so that the difference between this and `API_NOT_PUBLISHED` is
#: visible in the file that asserts on it.
PUBLISHED_API = {
    "status": "ready",
    "exposed_schema": "api",
    "max_rows": 500,
    "request_body_max_bytes": 1048576,
    "pool_size": 10,
    "connection_budget_reserved": 13,
    "api_surface_sha256": "1" * 64,
    "canonical_openapi_sha256": "2" * 64,
    "project_openapi_sha256": "3" * 64,
}

PUBLISHED_JWT = {
    "status": "ready",
    "issuer": "https://fixture-alpha-dev.test/api/app/auth",
    "audience": "urn:agentic-postgres:fixture-alpha:dev",
    "algorithm": "RS256",
    "active_kid": KID,
    "verification_kids": [KID],
    "public_jwks_sha256": "4" * 64,
    "temporary": True,
    "retire_after": None,
    # Version 9. Null rather than an empty object: no verifier has
    # acknowledged anything, which is what a deployment before its first
    # rotation looks like. An empty object would say every verifier had been
    # asked and none had answered.
    "verifier_acknowledgements": None,
}


def build(rendered: dict, **overrides):
    arguments = {
        "rendered": rendered,
        "source_commit": COMMIT,
        "health_status": "ready",
        # The version 5 default in this helper is the *unpublished* one, which
        # is what a session-3 deployment publishes and what `deployed_through_session`
        # below says this document is. The published shape is exercised by the
        # tests that pass it explicitly.
        "rest_status": "unavailable",
        "docs_status": "unavailable",
        # Version 9. Unpublished by default like the two above: a session-3
        # deployment serves no application route and no second documentation
        # surface, and D230 makes `unavailable` the honest state for a project
        # that has no administrator yet.
        "app_status": "unavailable",
        "app_docs_status": "unavailable",
        # Version 11, unpublished by default for the same reason and one more:
        # `unavailable` is what a project publishes until its R2 credential
        # validates (D326), so it is the state of every project that has not had
        # the Cloudflare step run for it -- which is all of them until Session 7
        # reaches a host.
        "storage_status": "unavailable",
        # Version 12, unpublished by default for the plainest reason of all: no
        # deployment anywhere publishes an agent plane yet, so `unavailable` with
        # `MCP_NOT_PUBLISHED` beside it is what every project on every host
        # records until Session 8's Run 7 gives it something to observe.
        "mcp_status": "unavailable",
        # Version 14, and `unavailable` by default for the plainest reason
        # of the lot: the `metrics` container carries `profiles:
        # [session14]`, so a deployment through anything earlier renders
        # the route, names it, and starts nothing behind it.
        "metrics_status": "unavailable",
        "api": deployed_output.API_NOT_PUBLISHED,
        "jwt": deployed_output.JWT_NOT_PUBLISHED,
        "mcp": deployed_output.MCP_NOT_PUBLISHED,
        # Required with no default in the builder, for the reason
        # `database_observed` is: a default would let a caller that deployed a
        # subset publish a document claiming the whole of it, and the systemd
        # launcher reads exactly this field at boot to decide what to restore.
        "deployed_through_session": 3,
        **OBSERVED,
        **overrides,
    }
    return deployed_output.build_deployed_document(**arguments)


def published(rendered: dict, **overrides):
    """A session-5 document: both routes serving, both blocks filled in."""
    arguments = {
        "rest_status": "ready",
        "docs_status": "ready",
        # Still unavailable: this helper describes a SESSION 5 deployment,
        # and the collector arrives nine sessions later.
        "metrics_status": "unavailable",
        "api": PUBLISHED_API,
        "jwt": PUBLISHED_JWT,
        "deployed_through_session": 5,
        **overrides,
    }
    return build(rendered, **arguments)


def test_it_builds_from_the_real_rendered_fixture(rendered: dict) -> None:
    document = build(rendered)
    assert document["document_kind"] == "deployed"
    # Derived rather than spelled: the previous form said 13, which was
    # right until it was not. A test that names the current version in a
    # literal has to be found by a failing run rather than by the bump.
    assert document["schema_version"] == deployed_output.SCHEMA_VERSION
    assert document["project"]["key"] == KEY


def test_the_deployed_document_carries_the_renders_lifecycle(rendered: dict) -> None:
    """Version 15 (ADR 0186). The deployed document repeats what the render
    said, verbatim -- a permanent fixture publishes `permanent`, and a render
    that said `ephemeral` with an expiry is published with both, so the fleet
    inventory reads the project's life off the host without the manifest. A
    builder that hardcoded `permanent` would pass the fixture and lie about
    every ephemeral project."""
    assert build(rendered)["project"]["lifecycle"] == {"kind": "permanent"}

    ephemeral = json.loads(json.dumps(rendered))
    ephemeral["project"]["lifecycle"] = {
        "kind": "ephemeral",
        "expires_at": "2999-01-01T00:00:00Z",
    }
    document = build(ephemeral)
    assert document["project"]["lifecycle"] == ephemeral["project"]["lifecycle"]
    deployed_output.validate_deployed_document(document)


def test_the_deployed_document_publishes_every_route_the_render_names(rendered: dict) -> None:
    """**The test that would have caught D395**, and would have caught D389.

    `routes.mcp` was in the RENDERED document from version 1 and in no DEPLOYED
    one until version 12. Eleven schema versions, two deployed projects, and a
    route every rendered document named and no deployed document mentioned --
    invisible because `build_deployed_document` assembles `routes` from an
    explicit key list, and a key list that is missing an entry looks exactly like
    a key list that is complete.

    **Compared as SETS, and that is the whole design of this test.** Every
    alternative fails in the same way:

    * A test naming the six routes it expects passes forever once written, and
      the seventh route is added to one branch only -- which is what happened.
    * A test asserting `deployed >= rendered` turns "publishes every route" into
      "publishes at least the ones I remembered", D300's exact shape.
    * A test comparing field by field never reaches a field that is absent from
      both sides of its own loop.

    Set equality is the only form where a route added to either branch and
    forgotten in the other fails, in either direction, without this test being
    edited. `health` is in both sets: its shape differs between the branches --
    an object here, an object there, a bare URL for the others -- and this
    compares names, not shapes.
    """
    document = build(rendered)

    assert set(document["routes"]) == set(rendered["routes"]), (
        "the rendered and deployed documents name different route sets. The rendered "
        "document is what a manifest produces and the deployed one is what every plane "
        "reads (ADR 0002); a route in one and not the other is either an address nobody "
        "can find a status for (D395) or a status for an address nothing derives"
    )


def test_the_deployed_document_carries_the_storage_settings(rendered: dict) -> None:
    """**The test that would have caught D389.**

    Version 11 put the storage bounds in the rendered document, and the deployed
    branch of the schema forbade them -- no property, `additionalProperties`
    false -- so a deployment published `routes.storage` and none of the bounds
    that route enforces. The first host gate found it through STO-BOUND-001,
    which reads `max_upload_bytes` from the deployed document rather than from a
    constant of its own, and found nothing to measure.

    Compared as a whole rather than member by member. A test naming the fields it
    expects would need editing whenever the block gains one, and would pass while
    the new one was dropped -- which is the failure it exists to catch.
    """
    document = build(rendered)

    assert document["storage"] == rendered["storage"], (
        "the deployed document must carry the rendered storage block unchanged: it is "
        "where the runtime reads the bounds it enforces (ADR 0002), and the rendered "
        "document is not what any plane reads"
    )


def test_the_deployed_document_publishes_a_bound_a_proof_can_measure(rendered: dict) -> None:
    """STO-BOUND-001's precondition, asserted where it is cheap to assert.

    The host proof failed with "the deployed document publishes no
    storage.max_upload_bytes, so there is no bound here to measure" -- a true
    statement about a broken document, and an expensive way to learn it, six
    minutes into a gate that needs a deployed host. The same fact is checkable
    here in milliseconds.
    """
    storage = build(rendered)["storage"]

    assert storage.get("max_upload_bytes"), (
        "no storage.max_upload_bytes in the deployed document, so STO-BOUND-001 has no "
        "bound to measure against"
    )
    assert storage["upload_url_ttl_seconds"] > 0
    assert storage["download_url_ttl_seconds"] > 0


def test_the_health_status_is_observed_and_not_carried_over(rendered: dict) -> None:
    """The rendered value is `planned`; it must not survive into a deployment."""
    assert rendered["routes"]["health"]["status"] == "planned"

    document = build(rendered, health_status="unavailable")
    assert document["routes"]["health"]["status"] == "unavailable"
    assert document["routes"]["health"]["url"] == rendered["routes"]["health"]["url"]


def test_a_rendered_health_status_is_refused(rendered: dict) -> None:
    """Guard the guard: `planned` must not validate as a deployed status."""
    with pytest.raises(ManifestError):
        build(rendered, health_status="planned")


def test_it_refuses_to_build_from_a_deployed_document(rendered: dict) -> None:
    """Building a deployment from a deployment would re-publish stale facts."""
    already = build(rendered)
    with pytest.raises(ManifestError, match="rendered"):
        build(already)


def test_the_direct_database_endpoint_stays_unavailable(rendered: dict) -> None:
    """SEC-NET-001 in the published document, not only in the firewall.

    Session 2 deploys no PostgreSQL. A deployed document that advertised a
    direct endpoint would contradict the chain that drops traffic to it.
    """
    document = build(rendered)
    assert document["database"]["direct"]["status"] == "unavailable"
    assert document["database"]["direct"]["url"] is None
    assert document["database"]["pooled"]["url"] is None


# ---------------------------------------------------------------------------
# Version 3: the observed block (ADR 0027)
# ---------------------------------------------------------------------------


def test_the_observed_block_is_the_callers_measurement(rendered: dict) -> None:
    """This module observes nothing; it records what it was handed."""
    document = build(rendered)
    assert document["database"]["observed"] == OBSERVED["database_observed"]


def test_the_derived_database_members_are_carried_not_rebuilt(rendered: dict) -> None:
    """Everything except `observed` comes from the render, unchanged.

    Re-deriving them here would be a second path to the same names, and the
    failure that produces is a deployed document describing a project the
    render never made -- ADR 0023's defect arriving from inside the tool.
    """
    document = build(rendered)
    for key in ("name", "container", "roles", "budget", "pooled", "direct"):
        assert document["database"][key] == rendered["database"][key], key


def test_a_deployment_that_measured_nothing_says_so(rendered: dict) -> None:
    """`NOT_OBSERVED` is a valid document, and it is distinguishable.

    Session 2's deploy path publishes this. The property that matters is that
    it cannot be mistaken for a cluster that was read and found empty.
    """
    document = build(rendered, database_observed=deployed_output.NOT_OBSERVED)
    observed = document["database"]["observed"]
    assert observed["status"] == "not_observed"
    assert observed["server_version"] is None
    assert observed["extensions"] is None
    assert observed["memory"] is None
    assert observed["instance_uuid"] is None


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"status": "not_observed", "server_version": "18.4"}, id="version-while-not"),
        pytest.param(
            {"status": "not_observed", "extensions": {"vector": "0.8.6"}}, id="ext-while-not"
        ),
        pytest.param(
            {"status": "not_observed", "memory": {"anon_mb": 1, "shmem_mb": 1, "file_mb": 1}},
            id="memory-while-not",
        ),
        pytest.param(
            {"status": "not_observed", "instance_uuid": INSTANCE_UUID},
            id="uuid-while-not",
        ),
    ],
)
def test_not_observed_cannot_carry_a_measurement(rendered: dict, broken: dict) -> None:
    """The half-filled block is the failure mode worth refusing.

    A status saying nothing was read, beside a value that could only have come
    from reading, is this repository's recurring defect in one object.
    """
    observed = {**deployed_output.NOT_OBSERVED, **broken}
    with pytest.raises(ManifestError):
        build(rendered, database_observed=observed)


def test_an_observed_block_is_required(rendered: dict) -> None:
    """Omitting it entirely must fail rather than default to a measurement."""
    document = build(rendered)
    del document["database"]["observed"]
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_the_deployed_document_carries_the_repository_and_an_honest_observation(
    rendered: dict,
) -> None:
    """Version 13. The settings are the rendered ones; the observation is not.

    `backup` is carried whole from the render because it is one `$def` shared by
    both branches (ADR 0146, D389). `backup_state` is measured, so a builder
    with no observer publishes `not_observed` -- and `NOT_OBSERVED`'s rule
    applies for its reason: a zero `wal_failed_count` here would be a claim that
    archiving is healthy, and indistinguishable from a real zero.
    """
    document = build(rendered)
    assert document["backup"] == rendered["backup"]
    assert document["backup_state"] == deployed_output.BACKUP_NOT_OBSERVED
    assert document["backup_state"]["status"] == "not_observed"
    deployed_output.validate_deployed_document(document)


def test_not_observed_forces_every_other_backup_member_null(rendered: dict) -> None:
    """The conditional is the whole value of the `not_observed` status.

    Without it a document could say "nothing has been observed" and carry a
    backup label beside it, which is the substitution `NOT_OBSERVED` exists to
    refuse -- stated in the schema rather than left to whoever writes the
    observer in Run 6.
    """
    document = build(rendered)
    document["backup_state"]["wal_failed_count"] = 0
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_a_rendered_document_cannot_carry_a_backup_state(rendered: dict) -> None:
    """ADR 0012, and the reason `backup_state` is a block of its own.

    An observation must be unrepresentable on the rendered branch rather than
    merely absent from it. `database` buys that with two `$defs` and pays a
    duplicated settings block for it; version 13 buys it by moving the
    observation out, so the settings stay one definition (D389).
    """
    smuggled = json.loads(json.dumps(rendered))
    smuggled["backup_state"] = dict(deployed_output.BACKUP_NOT_OBSERVED)
    with pytest.raises(ManifestError):
        config.validate_against_schema(smuggled, "outputs.schema.json")


def test_a_rendered_document_cannot_carry_an_observed_block(rendered: dict) -> None:
    """The rendered branch has no `observed`, so this must not validate.

    The two branches have separate definitions precisely so that this is a
    schema failure rather than a convention nobody checks (ADR 0012).
    """
    smuggled = json.loads(json.dumps(rendered))
    smuggled["database"]["observed"] = dict(deployed_output.NOT_OBSERVED)
    with pytest.raises(ManifestError):
        config.validate_against_schema(smuggled, "outputs.schema.json")


# ---------------------------------------------------------------------------
# Version 5: the published surface (ADR 0051, 0053)
# ---------------------------------------------------------------------------


def test_a_deployment_that_publishes_no_api_says_so(rendered: dict) -> None:
    """The three constants, and the property that makes them worth having.

    A session-4 deployment serves no REST and no documentation. What it must not
    do is describe that state in a way a reader could mistake for a published
    one -- so the routes name no URL, the API block names no schema, and the JWT
    block names no issuer.
    """
    document = build(rendered)
    assert document["routes"]["rest"] == {"status": "unavailable", "url": None}
    assert document["routes"]["docs"] == {"status": "unavailable", "url": None}
    assert document["api"] == deployed_output.API_NOT_PUBLISHED
    assert document["jwt"] == deployed_output.JWT_NOT_PUBLISHED


def test_a_published_route_carries_the_rendered_url_and_nothing_else(rendered: dict) -> None:
    """One URL, one derivation (ADR 0053).

    The deployed branch records a status against the render's URL rather than
    building a second one. Asserted by equality with the rendered document, so a
    future f-string here fails rather than agreeing until the base path changes.
    """
    document = published(rendered)
    assert document["routes"]["rest"]["url"] == rendered["routes"]["rest"]
    assert document["routes"]["docs"]["url"] == rendered["routes"]["docs"]
    assert document["routes"]["rest"]["status"] == "ready"


def test_an_unpublished_route_may_not_name_a_url(rendered: dict) -> None:
    """The schema half of the same rule, from the other direction."""
    document = published(rendered)
    document["routes"]["rest"]["status"] = "unavailable"
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_a_ready_route_may_not_have_a_null_url(rendered: dict) -> None:
    document = published(rendered)
    document["routes"]["docs"]["url"] = None
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_the_health_route_keeps_its_url_when_it_is_unavailable(rendered: dict) -> None:
    """`health` is deliberately the other case, and this says why in a test.

    Its address is the same string for every project at every session whether or
    not anything answers there, so nulling it would delete the thing an operator
    needs in order to go and look. `rest` and `docs` are different: before
    session 5 nothing is listening on either, so the URL would be describing a
    surface that does not exist.
    """
    document = build(rendered, health_status="unavailable")
    assert document["routes"]["health"]["url"] == rendered["routes"]["health"]["url"]


@pytest.mark.parametrize("status", ["planned", "issued", "ready ", ""])
def test_a_route_status_that_is_not_one_is_refused(rendered: dict, status: str) -> None:
    """`planned` is in this list for the reason the health status was.

    It is the rendered branch's word, it reads correctly, and copying it here
    would publish a manifest's intention as an observation.
    """
    with pytest.raises(ManifestError, match="'ready' or 'unavailable'"):
        build(rendered, rest_status=status)


def test_a_published_api_needs_a_published_route(rendered: dict) -> None:
    """The relation JSON Schema cannot state.

    Every field in a ready `api` block would still be true of a surface no
    request can arrive at, which is why this is checked rather than assumed.
    """
    with pytest.raises(ManifestError, match="no request can reach"):
        build(rendered, api=PUBLISHED_API, rest_status="unavailable")


def test_a_route_may_be_ready_while_the_api_block_is_not(rendered: dict) -> None:
    """The converse is legal, and deliberately so.

    A route that answers while the deploy could not read what it serves is a real
    state. Refusing it would push the deploy towards publishing the block it
    could not measure.
    """
    document = build(rendered, rest_status="ready")
    assert document["routes"]["rest"]["status"] == "ready"
    assert document["api"]["status"] == "unavailable"


def test_a_partially_filled_api_block_is_refused(rendered: dict) -> None:
    """`unavailable` with one real value is this project's recurring defect."""
    with pytest.raises(ManifestError):
        build(rendered, api={**deployed_output.API_NOT_PUBLISHED, "max_rows": 500})


def test_a_ready_api_block_may_not_be_hollow(rendered: dict) -> None:
    """And the other direction: `ready` with nulls would be a claim with no content."""
    with pytest.raises(ManifestError):
        published(rendered, api={**PUBLISHED_API, "canonical_openapi_sha256": None})


def test_the_active_key_must_be_one_a_verifier_accepts(rendered: dict) -> None:
    """Otherwise every token this issuer mints is refused by every verifier."""
    with pytest.raises(ManifestError, match="verification_kids"):
        published(rendered, jwt={**PUBLISHED_JWT, "verification_kids": ["c" * 43]})


def test_a_rotation_overlap_carries_at_most_two_keys(rendered: dict) -> None:
    """Two is the ceiling: an unbounded set is a set nobody retires from."""
    document = published(
        rendered,
        jwt={
            **PUBLISHED_JWT,
            "verification_kids": [KID, "c" * 43],
            "retire_after": "2026-09-01T00:00:00Z",
        },
    )
    assert document["jwt"]["retire_after"] == "2026-09-01T00:00:00Z"

    with pytest.raises(ManifestError):
        published(rendered, jwt={**PUBLISHED_JWT, "verification_kids": [KID, "c" * 43, "d" * 43]})


def test_a_symmetric_algorithm_is_not_representable(rendered: dict) -> None:
    """ADR 0051: a verifier that holds a signing key is an issuer.

    Refused by the schema rather than by a check somewhere in the issuer, because
    the document is what a verifier reads and it should not be able to describe a
    configuration where holding it is enough to mint.
    """
    with pytest.raises(ManifestError):
        published(rendered, jwt={**PUBLISHED_JWT, "algorithm": "HS256"})


def test_the_jwt_block_carries_no_private_material(rendered: dict) -> None:
    """Asserted on the key set, so a member added later has to be looked at."""
    document = published(rendered)
    assert set(document["jwt"]) == {
        "status",
        "issuer",
        "audience",
        "algorithm",
        "active_kid",
        "verification_kids",
        "public_jwks_sha256",
        "temporary",
        "retire_after",
        # Version 9, and looked at rather than waved through -- which is what
        # this test's key-set form exists to force. It carries a consumer name
        # and a sha256 of the public JWKS that consumer has loaded: an
        # identifier and a digest of public material, which is the same class of
        # thing as `public_jwks_sha256` beside it. No private JWK, no reference
        # to one, and nothing a verifier is not already entitled to hold.
        "verifier_acknowledgements",
    }
    deployed_output.validate_deployed_document(document)


def test_no_service_address_is_emitted(rendered: dict) -> None:
    """ADR 0053: `postgrest:3000` is the one field that would bypass the edge.

    The admin surface is absent for a different reason -- it binds container
    loopback and is not a network service -- and both absences are asserted on
    the document's bytes so that a helpfully-added convenience field fails here.
    """
    document = published(rendered)
    text = json.dumps(document)
    assert "postgrest:3000" not in text
    assert ":3001" not in text
    for url in (document["routes"]["rest"]["url"], document["routes"]["docs"]["url"]):
        assert url.startswith("https://")


def test_the_instance_uuid_is_the_one_the_registry_is_keyed_by(rendered: dict) -> None:
    """D106's debt, paid. The broker matches on this and nothing else."""
    document = published(rendered)
    assert document["database"]["observed"]["instance_uuid"] == INSTANCE_UUID

    document["database"]["observed"]["instance_uuid"] = INSTANCE_UUID.upper()
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_a_placeholder_the_schema_cannot_see_is_refused(rendered: dict) -> None:
    """The backstop, exercised on a field the schema leaves open.

    Most fields carry a pattern, so `<project-id>` is already refused as a
    malformed UUID — that path proves nothing about this guard. `template_version`
    is any string of one to sixty-four characters, which is exactly where an
    unfilled template survives validation and gets published as an observation.
    """
    document = build(rendered)
    document["template_version"] = "<version>"
    with pytest.raises(ManifestError, match="placeholder"):
        deployed_output.validate_deployed_document(document)


def test_a_constrained_field_is_refused_by_the_schema_first(rendered: dict) -> None:
    """The other half: patterns do most of the work, and should."""
    with pytest.raises(ManifestError):
        build(
            rendered,
            bootstrap={**OBSERVED["bootstrap"], "infisical_project_id": "<project-id>"},
        )


def test_a_secret_bearing_key_is_refused(rendered: dict) -> None:
    document = build(rendered)
    # S105: the point of this test is that the *key* is refused. The value is
    # deliberately not secret-shaped, so nothing is being hard-coded here.
    document["secrets"]["client_secret"] = "placeholder-for-a-rejected-key"  # noqa: S105
    with pytest.raises(ManifestError):
        deployed_output.validate_deployed_document(document)


def test_no_timestamp_rule_applies_to_rendered_documents_only(rendered: dict) -> None:
    """ADR 0013: this document describes a moment, so it carries one.

    The determinism assertion belongs to rendered output. Asserted here so the
    difference is deliberate rather than an oversight someone later "fixes".
    """
    document = build(rendered)
    assert document["observed_at"].endswith("Z")
    assert "observed_at" not in rendered


def test_it_is_written_owner_only(tmp_path: Path, rendered: dict) -> None:
    """It maps where the secrets are, even though it holds none of them."""
    path = deployed_output.write_deployed_document(build(rendered), tmp_path / "outputs.json")
    assert path.stat().st_mode & 0o777 == 0o600, oct(path.stat().st_mode)


def test_a_symlink_at_the_destination_is_refused(tmp_path: Path, rendered: dict) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "outputs.json"
    link.symlink_to(real)
    with pytest.raises(ManifestError, match="symlink"):
        deployed_output.write_deployed_document(build(rendered), link)


def test_the_recorded_paths_match_the_schema_patterns(rendered: dict) -> None:
    """release_path and state_directory are both constrained; both are built here."""
    document = build(rendered)
    assert document["runtime"]["release_path"].endswith(COMMIT)
    assert document["runtime"]["state_directory"].endswith(KEY)
    assert str(deployed_output.deployed_path(KEY)) == (
        f"/etc/agentic-postgres/projects/{KEY}/outputs.json"
    )


# ---------------------------------------------------------------------------
# The API plane is observed, not asserted (Run 9)
# ---------------------------------------------------------------------------


def deploy_module():
    """`bin/deploy-project.py`, imported for its pure observers.

    Importing it runs no deploy: everything at module scope is constants and
    function definitions, and `main()` is behind the usual guard.
    """
    import importlib.util

    source = REPO_ROOT / "bin" / "deploy-project.py"
    specification = importlib.util.spec_from_file_location("apg_deploy_under_test", source)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_the_api_block_refuses_for_each_reason_separately(tmp_path) -> None:
    """Two refusals, and until now only one of them was reachable.

    `api.status: ready` requires all three checksums -- the schema's own `else`
    branch -- so the block is `unavailable` when the reviewed snapshot is absent
    **and** when nothing answered on the route. Those are different facts and an
    operator needs to know which one happened.

    The first deploy of a project necessarily hits the first: the canonical
    snapshot is captured *from* a running deployment, reviewed by a human and
    committed, so it does not exist when the deploy that produces it runs. The
    redeploy at the approved commit is what publishes -- D112's two-deploy shape,
    arriving here for a second reason.

    **The snapshot path is a parameter for this test's sake, and that is a
    finding rather than a convenience.** It was read from a constant inside the
    function, so with no snapshot committed the first branch always fired, the
    second was dead code, and a mutation that deleted the served-document refusal
    stayed green. Both are reachable now and both are mutated.

    Goes red if: either refusal is dropped, or `ready` is claimed without all
    three checksums -- which the schema would reject on write, after the deploy
    has already published a service it cannot describe.
    """
    module = deploy_module()

    absent = tmp_path / "no-such-snapshot.json"
    assert module.observe_api(tmp_path, "0" * 64, absent) == deployed_output.API_NOT_PUBLISHED

    # A real snapshot, so the snapshot branch cannot be what refuses below.
    snapshot = tmp_path / "postgrest-openapi.canonical.json"
    snapshot.write_bytes(
        openapi_normalize.canonical_bytes(
            openapi_normalize.sort_maps(
                {
                    "swagger": "2.0",
                    "info": {"title": "x", "version": "1"},
                    "host": openapi_normalize.SENTINEL_HOST,
                    "basePath": openapi_normalize.SENTINEL_BASE_PATH,
                    "schemes": ["https"],
                    "paths": {"/": {}},
                }
            )
        )
    )
    assert module.observe_api(tmp_path, None, snapshot) == deployed_output.API_NOT_PUBLISHED


def test_the_jwt_block_carries_identifiers_and_never_key_material(tmp_path) -> None:
    """SEC-BOOT-001's shape, asserted on the observer rather than on a host.

    Every member is something a verifier may hold: an issuer, an audience, an
    algorithm, key *identifiers* and a digest of the public set. A private JWK
    parameter reaching this block would be signing material in a document that
    is copied off the host to run the external gate.

    The `kid` is read out of the rendered key set rather than recomputed, because
    that file is what PostgREST verifies against — a document naming a different
    one would describe a key set nothing is using.

    Goes red if: the block starts carrying a private parameter; `temporary`
    stops being true while the bootstrap issuer is still in use; or the active
    kid stops coming from the file.
    """
    module = deploy_module()

    assert (
        module.observe_jwt({}, tmp_path / "absent.json", issuer_is_temporary=True)
        == deployed_output.JWT_NOT_PUBLISHED
    )

    jwk = jwt_keys.public_jwk(modulus_hex="00" + "AB" * 256, exponent=65537)
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(jwt_keys.build_jwks([jwk]), indent=2), encoding="utf-8")

    rendered = {"jwt": {"issuer": "https://example.test/api/app/auth", "audience": "urn:a:b"}}
    block = module.observe_jwt(rendered, jwks, issuer_is_temporary=True)

    assert block["status"] == "ready"
    assert block["algorithm"] == jwt_keys.ALGORITHM
    assert block["active_kid"] == jwk["kid"]
    assert block["verification_kids"] == [jwk["kid"]]
    assert block["temporary"] is True
    assert block["retire_after"] is None
    assert len(block["public_jwks_sha256"]) == 64

    serialized = json.dumps(block)
    for private in jwt_keys.PRIVATE_JWK_PARAMETERS:
        assert f'"{private}"' not in serialized, private
    assert "BEGIN" not in serialized


def test_the_deploy_and_the_contract_command_name_one_snapshot() -> None:
    """Two files hold this path and only this compares them.

    `bin/deploy-project.py` records the reviewed snapshot's digest into
    `api.canonical_openapi_sha256`; `bin/api-contract.py --check` compares the
    live document against the snapshot. A deploy recording the digest of one file
    while the check command reads another is a disagreement that shows up as
    "the gate passes and the document is wrong", which is the least useful shape
    a failure can have.

    Goes red if: either path is edited alone. That is the same hazard D177
    recorded for the documentation route -- two derivations of one fact, in files
    that cannot see each other -- and the reason it is checked here rather than
    assumed.
    """
    import importlib.util

    def constant(name: str, alias: str) -> object:
        source = REPO_ROOT / "bin" / name
        specification = importlib.util.spec_from_file_location(alias, source)
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module.SNAPSHOT_PATH

    assert constant("deploy-project.py", "apg_deploy_snapshot") == constant(
        "api-contract.py", "apg_contract_snapshot"
    )


# ---------------------------------------------------------------------------
# The documentation route is observed, not asserted (Run 9a, ADR 0069)
# ---------------------------------------------------------------------------


class _Answer(http.server.BaseHTTPRequestHandler):
    """A server that answers however the test told it to.

    A real socket rather than a mock, for the reason every observer here is
    tested against one: the thing under test is what `urllib` does with a
    *response*, and a mock proves what the mock was written to prove. This is
    the same choice `test_edge_behaviour.py` makes one layer out.
    """

    status = 401
    challenge = 'Basic realm="docs"'

    def do_GET(self) -> None:
        body = b"nope\n"
        self.send_response(type(self).status)
        if type(self).challenge is not None:
            self.send_header("WWW-Authenticate", type(self).challenge)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@contextlib.contextmanager
def answering(status: int, challenge: str | None):
    _Answer.status = status
    _Answer.challenge = challenge
    server = http.server.HTTPServer(("127.0.0.1", 0), _Answer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/docs/rest"
    finally:
        server.shutdown()
        server.server_close()


def test_a_refusal_with_a_challenge_is_the_only_ready(tmp_path) -> None:
    """The positive control, and it has to come first.

    Without it, an observer that returned `unavailable` for everything would
    pass every refusal below and record an unpublished route for a route that
    works.
    """
    module = deploy_module()
    with answering(401, 'Basic realm="docs"') as url:
        assert module.observe_docs(url) == "ready"


def test_a_page_served_without_a_credential_is_never_ready(tmp_path) -> None:
    """The outcome that must never be recorded as published.

    200 here is worse than an unpublished route: the documentation is being
    served to anyone who asks, and `ready` would put that in a document
    automation reads as the boundary holding.
    """
    module = deploy_module()
    with answering(200, None) as url:
        assert module.observe_docs(url) == "unavailable"


@pytest.mark.parametrize(
    ("status", "challenge"),
    [
        (403, None),
        (404, None),
        (500, None),
        (502, None),
        # A non-401 that *does* offer a Basic challenge, and the reason this
        # case exists: with only the four above, the status check and the
        # challenge check are indistinguishable -- every one of them was
        # refused by the missing challenge, so deleting the status check
        # changed no outcome and a mutation walked through it. Only a response
        # that satisfies one check and not the other can tell them apart.
        (403, 'Basic realm="docs"'),
        (200, 'Basic realm="docs"'),
    ],
)
def test_a_status_that_is_neither_is_unavailable(
    status: int, challenge: str | None, tmp_path
) -> None:
    """404 in particular. Traefik's own 404 for an unrouted host is
    indistinguishable from a routed one from outside (D186), so the honest
    record is `unavailable` and the printed line says what came back."""
    module = deploy_module()
    with answering(status, challenge) as url:
        assert module.observe_docs(url) == "unavailable"


def test_a_refusal_with_no_challenge_is_unavailable(tmp_path) -> None:
    """A 401 a browser cannot act on, and what a half-resolved middleware chain
    produces -- which is the failure mode `@file` exists to prevent."""
    module = deploy_module()
    with answering(401, None) as url:
        assert module.observe_docs(url) == "unavailable"


def test_a_route_nothing_answers_on_is_unavailable_rather_than_an_exception() -> None:
    """A deploy that cannot describe its own route has still deployed.

    `check` handles an HTTP response; a connection that never became one -- DNS,
    TLS, refused -- would otherwise propagate out of step 7 and abort a deploy
    whose services are already running.
    """
    module = deploy_module()
    # Port 1 on loopback: nothing listens, and the refusal is immediate.
    assert module.observe_docs("http://127.0.0.1:1/docs/rest") == "unavailable"


def test_every_observation_reaches_the_published_document() -> None:
    """The boundary this project keeps dropping values at.

    `observe_docs` can be entirely correct and the deploy still hand
    `build_deployed_document` a literal -- which is what it did until Run 9a,
    honestly, because no service existed. D197 is the same shape (a manifest's
    timeouts validated and dropped at the rendering boundary) and so is D192 (a
    hook built, granted and never wired). Both were found on a host, months
    after the code was written.

    Asserted structurally rather than by grep: the call is parsed, and each
    status keyword must be a **name** -- something computed above -- rather than
    a constant. A literal here is exactly how a route that was observed `ready`
    gets published `unavailable`, and nothing else in the suite would notice.

    Goes red if: any of the three statuses is pinned to a literal at the call
    site, whatever the observer above it does.
    """
    import ast

    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "build_deployed_document"
    ]
    assert len(calls) == 1, f"expected one call to build_deployed_document, found {len(calls)}"

    supplied = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    for name in ("rest_status", "docs_status", "health_status"):
        assert name in supplied, f"{name} is not passed to the deployed document"
        assert isinstance(supplied[name], ast.Name), (
            f"{name} is passed as a literal, so whatever was observed above is discarded"
        )


def test_the_observer_delegates_to_the_operators_own_command() -> None:
    """One reading of "is this route published", not two.

    `bin/docs.py::check` is what an operator runs to ask the same question, and
    the deploy answering it differently is the shape D177 produced for the
    path -- two derivations, one comment claiming they were kept in step, and
    the one carrying the comment was the one that had not drifted.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    body = source[source.index("def observe_docs") :]
    body = body[: body.index("def observe_tls")]
    assert '_load_command("docs.py"' in body, "the deploy no longer asks bin/docs.py"
    assert "401" not in body.split('"""')[2], (
        "the observer restates the success condition instead of delegating it"
    )


def test_the_documentation_password_never_reaches_a_command_line() -> None:
    """One of the four places a secret must not be.

    The hash has to be produced in the locked runtime image -- `crypt` left the
    standard library in 3.13 and the host's interpreter is past that -- so a
    container is invoked, and the obvious way to invoke it puts the password in
    `argv` where `ps` and `docker inspect` can read it.

    Asserted structurally: the `subprocess.run` inside the publisher must pass
    the secret through `input=`, and no element of its argument list may
    mention the source file's contents. A `-i` flag is required for that to work
    at all; without it stdin is never attached and the container exits 0 having
    produced nothing.
    """
    import ast

    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "publish_edge_credentials"
    )
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    # **Every call, not the only one there used to be.** The publisher hashes
    # two credentials since version 14, and counting was never the property:
    # what matters is that no invocation puts a password in `argv`. A count
    # would have made a second CORRECT call look like a regression, while a
    # second incorrect one failed the same way and taught nobody which.
    assert calls, "the publisher hashes nothing; there is no credential to protect"

    for index, call in enumerate(calls):
        keywords = {keyword.arg for keyword in call.keywords}
        assert "input" in keywords, f"call {index}: the password is not passed on stdin"

        argv = call.args[0]
        assert isinstance(argv, ast.List)
        literals = [element.value for element in argv.elts if isinstance(element, ast.Constant)]
        assert "-i" in literals, (
            f"call {index}: docker was not given -i, so stdin is never attached"
        )
        assert not any("read_text" in ast.dump(element) for element in argv.elts), (
            f"call {index}: the credential is built into the argument vector"
        )


def test_the_publisher_writes_one_document_and_retires_the_one_it_replaced() -> None:
    """One artifact now, not two (ADR 0086), and the old one is unlinked.

    Stricter than the assertion it replaces, which required the publisher to
    write a users file *and* a middleware naming it. That pair is exactly what
    D252 was: the middleware named a path, so a rotation rewrote a file the
    parsed configuration did not mention and Traefik rebuilt nothing.

    Both names still come from `edge_credentials`, so the document the deploy
    writes and the file it removes cannot be given different names here.
    """
    import ast

    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "publish_edge_credentials"
    )
    body = ast.dump(function)
    assert "middleware_file_name" in body and "retired_users_file_name" in body, (
        "the publisher names one of the two files itself instead of asking edge_credentials"
    )
    assert body.count("_write_root_only") == 1, (
        "one document is written root-only, and there is no second file to write"
    )
    assert "unlink" in body, "the users file this design used to write is left on the host"


def _docker_reachable() -> bool:
    import subprocess

    try:
        return (
            subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                timeout=30,
                check=False,
            ).returncode
            == 0
        )
    except Exception:
        return False


@pytest.mark.skipif(
    not _docker_reachable(), reason="the Docker daemon is unreachable, so no hash can be produced"
)
def test_the_publisher_produces_a_credential_the_edge_can_use(tmp_path, monkeypatch) -> None:
    """The publisher, **run**, not described.

    Every other test of this function asserts the shape of the call it makes:
    the secret goes on stdin, `-i` is present, no element of the argument vector
    is built from the credential. All three were true while the program handed
    to `python -c` did not parse, and both deploys died on the host after two
    images had been built (D205).

    **One primitive is substituted and no more.** `_write_root_only` chowns to
    `root:root` and cannot run unprivileged; it is replaced by a plain write, and
    the two paths it is called with are recorded so the substitution cannot hide
    a file written under the wrong name. Everything else is real: the secret is
    read from a generation directory laid out the way the materializer lays one
    out, the hash is produced by the locked image, and the bcrypt check that
    would refuse a `$6$` is the product's own.

    Goes red if: the embedded program stops parsing, the image stops offering
    BLOWFISH, the hash stops satisfying the format Traefik accepts, or the
    middleware document stops naming the file the publisher writes.
    """
    module = deploy_module()

    password = "a1b2c3d4e5f60718293a4b5c6d7e8f90"  # noqa: S105
    generation = "0f4bfa6681b95217"
    project_key = "rehearsal-dev"

    root_plane = (
        tmp_path
        / "secrets"
        / project_key
        / "generations"
        / generation
        / secrets_contract.ROOT_PLANE_DIRECTORY
    )
    root_plane.mkdir(parents=True)
    # Trailing newline, because that is what the materializer writes and the
    # publisher has to strip it before hashing -- a hash of "password\n" is a
    # credential no operator can type.
    (root_plane / "docs_basic_auth_password").write_text(password + "\n", encoding="utf-8")
    # The second credential the publisher reads. A DIFFERENT value on
    # purpose: two that happened to match would let these pass while the
    # publisher hashed one password into both middlewares.
    (root_plane / "metrics_basic_auth_password").write_text(
        password + "-metrics\n", encoding="utf-8"
    )

    dynamic = tmp_path / "dynamic"
    written: dict[Path, bytes] = {}

    def record(path: Path, payload: bytes) -> None:
        written[path] = payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path / "secrets")
    monkeypatch.setattr(module, "EDGE_DYNAMIC_DIR", dynamic)
    monkeypatch.setattr(module, "_write_root_only", record)

    versions = (REPO_ROOT / "versions.env").read_text(encoding="utf-8")
    image = next(
        line.split("=", 1)[1]
        for line in versions.splitlines()
        if line.startswith("PYTHON_RUNTIME_IMAGE=")
    )

    module.publish_edge_credentials(
        project_key=project_key,
        generation_id=generation,
        middleware_name="apg-rehearsal-dev-docs-auth",
        metrics_middleware_name="apg-rehearsal-dev-metrics-auth",
        runtime_image=image,
    )

    middleware = dynamic / edge_credentials.middleware_file_name(project_key)
    assert set(written) == {middleware}, (
        f"the publisher wrote {sorted(p.name for p in written)}, not the one document the "
        "file provider parses"
    )

    document = yaml.safe_load(middleware.read_text(encoding="utf-8"))
    basic = document["http"]["middlewares"]["apg-rehearsal-dev-docs-auth"]["basicAuth"]
    assert "usersFile" not in basic, "the indirection D252 was caused by is back"

    (entry,) = basic["users"]
    user, _, hashed = entry.partition(":")
    assert user == edge_credentials.DOCS_USER
    # The product's own check, so this cannot pass on a format Traefik answers
    # 401 to in a way indistinguishable from a wrong password (D165).
    edge_credentials.assert_bcrypt(hashed)

    assert basic["removeHeader"] is True


@pytest.mark.skipif(
    not _docker_reachable(), reason="the Docker daemon is unreachable, so no hash can be verified"
)
def test_the_published_hash_verifies_against_its_own_password_and_no_other(
    tmp_path, monkeypatch
) -> None:
    """The control the test above needs.

    A publisher that wrote a well-formed hash of the *wrong bytes* -- the
    password with its trailing newline still attached, say -- satisfies every
    format assertion and refuses the operator at the door.
    """
    import subprocess

    module = deploy_module()
    password = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"  # noqa: S105
    generation = "gen"
    project_key = "rehearsal-two-dev"

    root_plane = (
        tmp_path
        / "secrets"
        / project_key
        / "generations"
        / generation
        / secrets_contract.ROOT_PLANE_DIRECTORY
    )
    root_plane.mkdir(parents=True)
    (root_plane / "docs_basic_auth_password").write_text(password + "\n", encoding="utf-8")
    # The second credential the publisher reads. A DIFFERENT value on
    # purpose: two that happened to match would let these pass while the
    # publisher hashed one password into both middlewares.
    (root_plane / "metrics_basic_auth_password").write_text(
        password + "-metrics\n", encoding="utf-8"
    )

    dynamic = tmp_path / "dynamic"

    def record(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    monkeypatch.setattr(module, "SECRET_ROOT", tmp_path / "secrets")
    monkeypatch.setattr(module, "EDGE_DYNAMIC_DIR", dynamic)
    monkeypatch.setattr(module, "_write_root_only", record)

    versions = (REPO_ROOT / "versions.env").read_text(encoding="utf-8")
    image = next(
        line.split("=", 1)[1]
        for line in versions.splitlines()
        if line.startswith("PYTHON_RUNTIME_IMAGE=")
    )
    module.publish_edge_credentials(
        project_key=project_key,
        generation_id=generation,
        middleware_name="m",
        metrics_middleware_name="m-metrics",
        runtime_image=image,
    )

    published = yaml.safe_load(
        (dynamic / edge_credentials.middleware_file_name(project_key)).read_text(encoding="utf-8")
    )
    (entry,) = published["http"]["middlewares"]["m"]["basicAuth"]["users"]
    hashed = entry.partition(":")[2]

    def verifies(candidate: str) -> bool:
        finished = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "-e",
                f"APG_CANDIDATE={candidate}",
                image,
                "python",
                "-c",
                "import crypt,os,sys;h=sys.stdin.read().strip();"
                'print(crypt.crypt(os.environ["APG_CANDIDATE"], h) == h)',
            ],
            input=hashed,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return finished.stdout.strip() == "True"

    assert verifies(password), "the operator's own password does not open the page"
    assert not verifies(password + "\n"), "the trailing newline was hashed into the credential"
    assert not verifies("not-the-password")


# ---------------------------------------------------------------------------
# A producer of a schema-constrained block supplies every key of it (D251)
# ---------------------------------------------------------------------------


def _load_deploy_command():
    """`bin/deploy-project.py` is a script, not a module. Load it by path."""
    import importlib.util

    source = REPO_ROOT / "bin" / "deploy-project.py"
    spec = importlib.util.spec_from_file_location("apg_deploy_project_under_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_properties(name: str) -> set[str]:
    import json

    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    return set(schema["$defs"][name]["properties"])


def test_the_not_published_constants_carry_every_key_of_their_schema_block() -> None:
    """`additionalProperties: false` plus a full `required` list means equality."""
    from agentic_postgres import deployed_output

    for constant, definition in (
        (deployed_output.JWT_NOT_PUBLISHED, "deployedJwt"),
        (deployed_output.API_NOT_PUBLISHED, "deployedApi"),
        (deployed_output.ROUTE_NOT_PUBLISHED, "publishedRoute"),
    ):
        assert set(constant) == _schema_properties(definition), definition


def test_observe_jwt_produces_every_key_the_schema_requires(tmp_path: Path) -> None:
    """The one that failed on a live host, twice in one window.

    Version 9 added `jwt.verifier_acknowledgements`. `JWT_NOT_PUBLISHED` gained
    it, the test fixture gained it, and **`observe_jwt` -- the function the deploy
    actually calls when the issuer IS published -- did not**. The document
    validated in every offline test, because every offline test built its jwt
    block from the constant or the fixture, and failed schema validation on the
    host at step 7.

    So this calls the producer. Not a re-reading of the constant beside it: the
    constant was right both times.
    """
    import json

    deploy = _load_deploy_command()

    jwks = tmp_path / "jwks.json"
    jwks.write_text(
        json.dumps({"keys": [{"kid": "a" * 43, "kty": "RSA", "alg": "RS256"}]}), encoding="utf-8"
    )
    rendered = {
        "jwt": {
            "issuer": "https://example.test/api/app/auth",
            "audience": "urn:agentic-postgres:example:dev",
        }
    }

    produced = deploy.observe_jwt(rendered, jwks, issuer_is_temporary=True)
    assert set(produced) == _schema_properties("deployedJwt"), (
        "observe_jwt does not produce the deployedJwt block the schema describes. A key "
        "added to the schema and to JWT_NOT_PUBLISHED but not here fails only on a "
        "deployment that actually publishes an issuer"
    )
    assert produced["status"] == "ready"


def test_observe_jwt_and_the_absent_constant_agree_on_shape(tmp_path: Path) -> None:
    """Two producers of one block. The pair is what the schema sees.

    They differ in every value and must agree in every key: one describes an
    issuer that is published and the other one that is not, and a reader of the
    document cannot be asked to know which shape it is holding.
    """
    import json

    from agentic_postgres import deployed_output

    deploy = _load_deploy_command()
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{"kid": "b" * 43}]}), encoding="utf-8")

    produced = deploy.observe_jwt(
        {"jwt": {"issuer": "https://example.test/a", "audience": "urn:x:y:z"}},
        jwks,
        issuer_is_temporary=True,
    )
    assert set(produced) == set(deployed_output.JWT_NOT_PUBLISHED)


def test_observe_jwt_reports_absence_when_there_is_no_key_set(tmp_path: Path) -> None:
    """The other branch, and it returns the constant -- so it is covered above."""
    from agentic_postgres import deployed_output

    deploy = _load_deploy_command()
    produced = deploy.observe_jwt({"jwt": {}}, tmp_path / "absent.json", issuer_is_temporary=True)
    assert produced == deployed_output.JWT_NOT_PUBLISHED


# ---------------------------------------------------------------------------
# What a deploy carries forward, and what it observes (Run 10)
# ---------------------------------------------------------------------------


def test_the_rotation_state_survives_a_deploy(tmp_path, monkeypatch) -> None:
    """`retire_after` and `verifier_acknowledgements` are not derivable.

    A deadline is a moment a promotion chose and an acknowledgement is what a
    verifier reported; neither is written anywhere on disk except the deployed
    document. A deploy that reset them would silently block a promotion that had
    already been earned, and an operator would re-run the acknowledgement step
    wondering why it did not take.
    """
    module = deploy_module()
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{"kid": "a" * 43}, {"kid": "b" * 43}]}), encoding="utf-8")
    rendered = {"jwt": {"issuer": "https://probe.test/api/app/auth", "audience": "urn:x:y:z"}}
    previous = {
        "retire_after": "2026-08-11T12:05:30Z",
        "verifier_acknowledgements": {"postgrest": "c" * 64},
    }

    block = module.observe_jwt(rendered, jwks, previous, issuer_is_temporary=True)
    assert block["retire_after"] == "2026-08-11T12:05:30Z"
    assert block["verifier_acknowledgements"] == {"postgrest": "c" * 64}

    # The control: with no previous document there is nothing to carry, and the
    # deploy must not invent a deadline.
    fresh = module.observe_jwt(rendered, jwks, {}, issuer_is_temporary=True)
    assert fresh["retire_after"] is None
    assert fresh["verifier_acknowledgements"] is None


def test_a_retired_rotation_does_not_carry_its_deadline_forward(tmp_path) -> None:
    """A deadline is about a key that is still published.

    Once the set is back to one key the overlap has ended, and a deadline
    describing it would be refused by `validate_key_state` -- correctly, and on
    a document the deploy had already written.
    """
    module = deploy_module()
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{"kid": "a" * 43}]}), encoding="utf-8")
    rendered = {"jwt": {"issuer": "https://probe.test/api/app/auth", "audience": "urn:x:y:z"}}

    block = module.observe_jwt(
        rendered,
        jwks,
        {"retire_after": "2026-08-11T12:05:30Z", "verifier_acknowledgements": {}},
        issuer_is_temporary=True,
    )
    assert block["retire_after"] is None
    assert block["verifier_acknowledgements"] is None


def test_the_application_route_is_not_published_without_an_administrator(monkeypatch) -> None:
    """D230, and the reason it is a status rather than a state machine.

    The first request to reach a published application route with no
    administrator is the request that decides who the administrator is. D135
    refused inventing a deployment state for that; every route already has a
    status field, and `publishedRoute` forces a null URL when it is
    `unavailable`.

    **The route is made to answer correctly, and the answer is still
    `unavailable`.** The first version of this test called `observe_app` with
    the real `run()` against a hostname that does not resolve, so the curl
    failed and the function returned `unavailable` for that reason -- it passed
    with the administrator gate deleted. Found by the mutation battery, and it
    is D173's shape: an assertion that could not fail.
    """
    module = deploy_module()

    class Refusing:
        stdout = "401"
        stderr = ""
        returncode = 0

    monkeypatch.setattr(module, "run", lambda *command: Refusing())
    assert module.observe_app("https://probe.test/api/app", administrator=False) == "unavailable", (
        "the route answered exactly as a published one should and was published, so the "
        "administrator gate is not doing anything"
    )


def test_the_application_route_is_published_only_when_it_refuses(monkeypatch) -> None:
    """The control for the test above, and the same shape `observe_docs` uses.

    A 401 from `/auth/me` proves the router matched, the strip worked -- FastAPI
    saw `/auth/me` rather than `/api/app/auth/me`, which would be a 404 -- and
    the service refused. A 200 anywhere would prove less.
    """
    module = deploy_module()

    class Result:
        def __init__(self, status: str) -> None:
            self.stdout = status
            self.stderr = ""
            self.returncode = 0

    monkeypatch.setattr(module, "run", lambda *command: Result("401"))
    assert module.observe_app("https://probe.test/api/app", administrator=True) == "ready"

    monkeypatch.setattr(module, "run", lambda *command: Result("200"))
    assert module.observe_app("https://probe.test/api/app", administrator=True) == "unavailable"

    monkeypatch.setattr(module, "run", lambda *command: Result("404"))
    assert module.observe_app("https://probe.test/api/app", administrator=True) == "unavailable"


def test_the_administrator_probe_interpolates_through_psql_rather_than_python() -> None:
    """Measured: `psql -c` performs NO variable interpolation.

    `SET ROLE :"admin_owner"` passed with `-c` reached the server verbatim and
    failed with `syntax error at or near ":"`. On stdin the same two lines
    interpolate -- `current_user` came back as the owner, a role nothing names
    counted 0 rather than erroring, and `x' OR '1'='1` as the literal counted 0
    rather than every row. That is why `bin/auth-admin.py` reads its SQL from
    stdin too, and why a role name is never concatenated into this query.
    """
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "observe_active_administrator"
    )
    body = ast.dump(function)
    assert "arg='input'" in body, (
        "the SQL is not sent on stdin, and psql interpolates no variable in a string "
        'passed with -c -- measured, `SET ROLE :"admin_owner"` reached the server '
        'verbatim and failed with `syntax error at or near ":"`'
    )
    assert "admin_owner=" in body and "admin_role=" in body, (
        "the query's two names are not passed as psql variables"
    )
    statement = next(
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "statement" for t in node.targets)
    )
    assert isinstance(statement, ast.Constant), (
        "the probe's SQL is built with an f-string; a role name is being concatenated "
        "into a query that psql can quote for it"
    )


# ---------------------------------------------------------------------------
# Which roles a deployed document says can log in (Session 7 Run 4)
# ---------------------------------------------------------------------------
#
# **These exist because a mutation battery found the clauses untestable.** The
# derivation lived inline in `test_only_the_activated_roles_may_log_in`, which is
# gated on `APG_LIVE_HOST`, so mutating any clause left the whole offline suite
# green. It is a pure function over a dict; "the suite cannot drive this" was
# never true, only "nothing had" -- D211-D214's condition.
#
# Written as a table over synthetic documents rather than as one happy-path
# assertion, because the dangerous half is every row that must NOT activate a
# role. The documents are deliberately not real renders: several of these
# combinations cannot occur on one deployment, which is exactly why a live host
# cannot test them.

LOGIN_ROLES = {
    "migration_user": "apg_x_migration_user",
    "postgrest_authenticator": "apg_x_postgrest_authenticator",
    "auth_service": "apg_x_auth_service",
    "storage_service": "apg_x_storage_service",
    "app_runtime": "apg_x_app_runtime",
    # Session 10 Run 5, and D517 **predicted** this line rather than discovering
    # it. `backup_user` has been in `naming.ROLE_SUFFIXES` since Session 3 as a
    # NOLOGIN stub; ADR 0148 activates it, so the derivation has to say so or
    # `test_only_the_activated_roles_may_log_in` reports the product's own
    # deliberate activation as a violation on the next host gate -- which is
    # exactly what D301 cost after `project_admin`.
    "backup_user": "apg_x_backup_user",
}


def _login_document(
    *,
    profiles: dict | None = None,
    rest_status: str | None = None,
    app_route: object = None,
    required_names: list[str] | None = None,
) -> dict:
    document: dict = {"database": {"access_profiles": profiles or {}}, "routes": {}, "secrets": {}}
    if rest_status is not None:
        document["routes"]["rest"] = {"status": rest_status, "url": None}
    if app_route is not None:
        document["routes"]["app"] = app_route
    if required_names is not None:
        document["secrets"]["required_names"] = required_names
    return document


def test_a_bare_deployment_activates_only_the_migration_user() -> None:
    """Session 3's own activation, and the floor every other row is measured
    against. If this returned more, every assertion below would hold for a
    reason that has nothing to do with its own clause."""
    assert deployed_output.activated_login_roles(_login_document(), LOGIN_ROLES) == {
        LOGIN_ROLES["migration_user"]
    }


def test_an_available_access_profile_activates_its_role() -> None:
    activated = deployed_output.activated_login_roles(
        _login_document(
            profiles={"runtime_pooled": {"role": LOGIN_ROLES["app_runtime"], "status": "available"}}
        ),
        LOGIN_ROLES,
    )
    assert LOGIN_ROLES["app_runtime"] in activated


def test_an_unavailable_access_profile_does_not() -> None:
    """The control for the row above. A derivation that added every profile's
    role regardless of status would pass that test and would then demand LOGIN
    from a role no session has activated."""
    activated = deployed_output.activated_login_roles(
        _login_document(
            profiles={
                "runtime_pooled": {"role": LOGIN_ROLES["app_runtime"], "status": "unavailable"}
            }
        ),
        LOGIN_ROLES,
    )
    assert LOGIN_ROLES["app_runtime"] not in activated


@pytest.mark.parametrize(
    ("status", "activated"),
    [("ready", True), ("unavailable", False)],
)
def test_the_rest_route_activates_the_authenticator_only_when_ready(
    status: str, activated: bool
) -> None:
    """D211: the authenticator is not an access profile, so without this clause
    it is activated, correct, and invisible to the document."""
    result = deployed_output.activated_login_roles(_login_document(rest_status=status), LOGIN_ROLES)
    assert (LOGIN_ROLES["postgrest_authenticator"] in result) is activated


def test_an_application_route_activates_the_auth_service() -> None:
    result = deployed_output.activated_login_roles(
        _login_document(app_route={"status": "unavailable", "url": None}), LOGIN_ROLES
    )
    assert LOGIN_ROLES["auth_service"] in result, (
        "an application route that is present but not ready still means the auth container "
        "is authenticating as this role -- the route's presence is the event, not its status"
    )


def test_no_application_route_leaves_the_auth_service_inactive() -> None:
    result = deployed_output.activated_login_roles(_login_document(), LOGIN_ROLES)
    assert LOGIN_ROLES["auth_service"] not in result


def test_the_storage_role_is_keyed_on_the_credential_and_not_on_the_route() -> None:
    """**The row that would have failed a correct deployment** (D307, D280).

    `routes.storage` is present in every v11 document, and v11 was published
    while `CURRENT_SESSION` was still 6 -- so a deploy at session 6 renders a
    storage route, materializes no storage secret, and correctly leaves the role
    NOLOGIN. Keying on the route would have demanded LOGIN from it and turned a
    correct deployment red.

    This document has the route and not the credential, which is exactly that
    deployment, and it cannot be produced on a host today to check by hand.
    """
    document = _login_document(required_names=["session2_sentinel"])
    document["routes"]["storage"] = {"status": "unavailable", "url": None}

    result = deployed_output.activated_login_roles(document, LOGIN_ROLES)
    assert LOGIN_ROLES["storage_service"] not in result, (
        "the storage role is expected to log in on a deployment that never materialized its "
        "credential. The key is `secrets.required_names`, not the route"
    )


def test_the_storage_credential_in_the_generation_activates_the_role() -> None:
    """The other half. Without it the clause could be `if False` and every other
    row here would still pass -- which is precisely what the battery's M5 was."""
    result = deployed_output.activated_login_roles(
        _login_document(required_names=["session2_sentinel", "storage_service_password"]),
        LOGIN_ROLES,
    )
    assert LOGIN_ROLES["storage_service"] in result


def test_the_backup_role_is_keyed_on_the_credential_and_not_on_the_manifest_flag() -> None:
    """The storage row's shape, applied to Session 10's activation (D517).

    `backup.enabled` is the tempting key and it is the wrong one: the bootstrap
    plane never reads it. `activate_backup_user` credentials the role when the
    active generation carries the file and leaves it NOLOGIN when it does not,
    so the credential is the event and the manifest flag is a different question.

    **There is no route to key on either**, which is what makes this row
    different from the storage one rather than a copy of it: a repository is not
    an HTTP surface, so the mistake D307 caught for storage is not available here.
    The mistake that IS available is keying on `backup.enabled`, and this
    document is a project with backups enabled whose secret has not been
    materialized -- which is every project's state on the first Session 10 deploy.
    """
    document = _login_document(required_names=["session2_sentinel"])
    document["backup"] = {"enabled": True, "retain_full": 2}

    result = deployed_output.activated_login_roles(document, LOGIN_ROLES)
    assert LOGIN_ROLES["backup_user"] not in result, (
        "the backup role is expected to log in on a deployment that never materialized its "
        "credential. The key is `secrets.required_names`, not `backup.enabled` -- and the "
        "first deploy of every project is in exactly this state"
    )


def test_the_backup_credential_in_the_generation_activates_the_role() -> None:
    """The other half. Without it the clause could be `if False` and every other
    row here would still pass -- which is precisely what the storage battery's
    M5 was, and the reason that pair is written as a pair."""
    result = deployed_output.activated_login_roles(
        _login_document(required_names=["session2_sentinel", "backup_user_password"]),
        LOGIN_ROLES,
    )
    assert LOGIN_ROLES["backup_user"] in result


def test_a_full_session_ten_deployment_activates_every_service_identity() -> None:
    """All six clauses at once, so a derivation that handled them only in
    isolation is caught.

    Six since Run 5. The assertion is `== set(LOGIN_ROLES.values())` rather than
    a list written here, so adding a role to the table without adding a clause
    that activates it fails here -- which is the direction this test is for.
    """
    result = deployed_output.activated_login_roles(
        _login_document(
            profiles={
                "runtime_pooled": {"role": LOGIN_ROLES["app_runtime"], "status": "available"}
            },
            rest_status="ready",
            app_route={"status": "ready", "url": "https://x.test/api/app"},
            required_names=["storage_service_password", "backup_user_password"],
        ),
        LOGIN_ROLES,
    )
    assert result == set(LOGIN_ROLES.values())


def test_the_issuer_is_temporary_only_while_its_credential_is_still_issued(
    tmp_path: Path,
) -> None:
    """`jwt.temporary` is published, not asserted (ADR 0170).

    **It was the literal `True` for ten sessions.** The comment above it read
    "True until Session 6 replaces the issuer" -- written before Session 6, never
    revisited after it shipped -- so the deployed document called the issuer
    temporary while its replacement was already live, and `SEC-BOOT-001`'s branch
    on the false case could not execute. A value that looks measured and is not.

    **Both values are asserted here, and that is the point.** A proof that only
    ever passed `True` would pass just as happily against the constant this
    replaces, which is the exact defect it exists to catch. The two calls differ
    in one argument and nothing else.
    """
    module = _load_deploy_command()
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": [{"kid": "c" * 43}]}), encoding="utf-8")
    rendered = {"jwt": {"issuer": "https://probe.test/api/app/auth", "audience": "urn:x:y:z"}}

    live = module.observe_jwt(rendered, jwks, {}, issuer_is_temporary=True)
    retired = module.observe_jwt(rendered, jwks, {}, issuer_is_temporary=False)

    assert live["temporary"] is True
    assert retired["temporary"] is False, (
        "observe_jwt publishes `temporary` regardless of what it was told, which is the "
        "hard-coded True this replaced"
    )

    # And nothing else moved: the flag describes the issuer's lifecycle, not the
    # key set. Two documents differing in more than one field would mean the
    # retirement had reached something it does not own.
    assert {k: v for k, v in live.items() if k != "temporary"} == {
        k: v for k, v in retired.items() if k != "temporary"
    }
