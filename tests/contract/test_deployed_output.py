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

from agentic_postgres import REPO_ROOT, deployed_output
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
        "state_directory": f"/var/lib/agentic-postgres/projects/{KEY}",
        "compose_model_sha256": "d" * 64,
    },
}


def build(rendered: dict, **overrides):
    arguments = {
        "rendered": rendered,
        "source_commit": COMMIT,
        "health_status": "ready",
        **OBSERVED,
        **overrides,
    }
    return deployed_output.build_deployed_document(**arguments)


def test_it_builds_from_the_real_rendered_fixture(rendered: dict) -> None:
    document = build(rendered)
    assert document["document_kind"] == "deployed"
    assert document["schema_version"] == 2
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
        f"/var/lib/agentic-postgres/projects/{KEY}/outputs.json"
    )
