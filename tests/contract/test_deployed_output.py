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

import json
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, config, deployed_output, jwt_keys, openapi_normalize
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
        "api": deployed_output.API_NOT_PUBLISHED,
        "jwt": deployed_output.JWT_NOT_PUBLISHED,
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
        "api": PUBLISHED_API,
        "jwt": PUBLISHED_JWT,
        "deployed_through_session": 5,
        **overrides,
    }
    return build(rendered, **arguments)


def test_it_builds_from_the_real_rendered_fixture(rendered: dict) -> None:
    document = build(rendered)
    assert document["document_kind"] == "deployed"
    assert document["schema_version"] == 7
    assert document["project"]["key"] == KEY


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

    assert module.observe_jwt({}, tmp_path / "absent.json") == deployed_output.JWT_NOT_PUBLISHED

    jwk = jwt_keys.public_jwk(modulus_hex="00" + "AB" * 256, exponent=65537)
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps(jwt_keys.build_jwks([jwk]), indent=2), encoding="utf-8")

    rendered = {"jwt": {"issuer": "https://example.test/api/app/auth", "audience": "urn:a:b"}}
    block = module.observe_jwt(rendered, jwks)

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
