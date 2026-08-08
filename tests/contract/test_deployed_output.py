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

from agentic_postgres import REPO_ROOT, config, deployed_output
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

KEY = "fixture-alpha-dev"
COMMIT = "a" * 40


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
    },
}


def build(rendered: dict, **overrides):
    arguments = {
        "rendered": rendered,
        "source_commit": COMMIT,
        "health_status": "ready",
        # Required with no default in the builder, for the reason
        # `database_observed` is: a default would let a caller that deployed a
        # subset publish a document claiming the whole of it, and the systemd
        # launcher reads exactly this field at boot to decide what to restore.
        "deployed_through_session": 3,
        **OBSERVED,
        **overrides,
    }
    return deployed_output.build_deployed_document(**arguments)


def test_it_builds_from_the_real_rendered_fixture(rendered: dict) -> None:
    document = build(rendered)
    assert document["document_kind"] == "deployed"
    assert document["schema_version"] == 3
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
