"""Provider bootstrap state contract (Session 2, Phase 4).

The interesting assertions are about what state *cannot* say. Bootstrap is the
one command allowed to create and destroy external resources, so the failure
modes here are not "a field is wrong" — they are "one project destroys another
project's provider resources" and "a client secret is leaked because state and
disk disagreed".

Nothing here contacts a provider. `bin/bootstrap-providers.sh` lands in Run 4;
this is the state contract it will have to satisfy.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, bootstrap_state, config, host_config
from agentic_postgres.bootstrap_state import BootstrapStateError

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def make_state(project_key: str = "alpha-dev") -> dict[str, Any]:
    """A minimal valid state document.

    Built here rather than committed as a fixture because a committed example
    of this file would be a committed map of a real provider organization.
    """
    return {
        "schema_version": 1,
        "project_key": project_key,
        "project_manifest_sha256": "a" * 64,
        "provider_inputs_sha256": "b" * 64,
        "provider": "infisical",
        "api_url": "https://app.infisical.com",
        "organization_slug": "example-team",
        "infisical_project_id": "prj-0123456789",
        "environment_slug": "dev",
        "runtime_folder": "/runtime",
        "runtime_identity_id": "idn-0123456789",
        "runtime_client_id": "cli-0123456789",
        "active_client_secret_id": "sec-0123456789",
        "credential_files": bootstrap_state.credential_paths(project_key),
        "managed_resources": [
            "project",
            "environment",
            "runtime_folder",
            "runtime_identity",
            "runtime_membership",
            "runtime_client_secret",
            "session2_sentinel",
        ],
        "created_at": "2026-08-04T10:00:00Z",
        "updated_at": "2026-08-04T10:00:00Z",
    }


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_a_well_formed_state_document_validates() -> None:
    bootstrap_state.validate_state(make_state())


def test_state_carries_no_secret_bearing_key() -> None:
    """`runtime_client_id` is a username. A client secret is not in this file.

    Note that `active_client_secret_id` survives the sensitive-key rule because
    it ends in `_id` under terminal-token matching (ADR 0008) -- and it should,
    because it is an identifier for a secret, not a secret.
    """
    config.assert_no_sensitive_keys(make_state())


def test_an_unknown_field_is_rejected() -> None:
    document = make_state()
    document["client_secret_value"] = "st.abc"  # noqa: S105
    with pytest.raises(config.ManifestError):
        bootstrap_state.validate_state(document)


def test_an_unknown_managed_resource_is_rejected() -> None:
    """Destruction reads this list; a typo that widened it is the worst bug here."""
    document = make_state()
    document["managed_resources"].append("everything")
    with pytest.raises(config.ManifestError):
        bootstrap_state.validate_state(document)


def test_state_paths_are_project_scoped() -> None:
    assert bootstrap_state.state_path("alpha-dev") == Path(
        "/etc/agentic-postgres/projects/alpha-dev/bootstrap-state.json"
    )
    expected = "/etc/agentic-postgres/credentials/alpha-dev/infisical-client-secret"
    assert bootstrap_state.credential_paths("alpha-dev")["client_secret_path"] == expected


def test_the_credential_path_fields_are_named_for_what_they_hold() -> None:
    """The `_path` suffix is load-bearing, not decoration.

    A key literally named `client_secret` is rejected by ADR 0008's terminal-token
    rule -- correctly, because the rule cannot tell that this one holds a
    filename. The runbook's Phase 4 fragment uses the bare names; renaming the
    fields satisfies the inherited rule without weakening it, which is the
    outcome the rule is supposed to produce.
    """
    assert set(bootstrap_state.credential_paths("alpha-dev")) == {
        "client_id_path",
        "client_secret_path",
    }
    for field in bootstrap_state.credential_paths("alpha-dev"):
        assert not config.is_sensitive_key(field)
    assert config.is_sensitive_key("client_secret")


# ---------------------------------------------------------------------------
# Cross-project confusion — the failure that matters
# ---------------------------------------------------------------------------


def test_state_may_not_name_another_projects_credential_directory() -> None:
    """Runbook §15: 'Project B is configured to use Project A's credential directory'.

    Without this check, B's materializer would authenticate as A and read A's
    secrets, and every path in the resulting generation would still look
    correctly scoped to B.
    """
    document = make_state("beta-dev")
    document["credential_files"] = bootstrap_state.credential_paths("alpha-dev")
    with pytest.raises(BootstrapStateError, match="outside its own directory"):
        bootstrap_state.validate_state(document)


def test_a_credential_path_outside_the_credential_root_is_rejected() -> None:
    document = make_state()
    # S105/S108: a path outside the credential root, present so the schema's
    # anchored pattern can be shown to reject it.
    outside = "/tmp/infisical-client-secret"  # noqa: S108
    document["credential_files"]["client_secret_path"] = outside
    with pytest.raises(config.ManifestError):
        bootstrap_state.validate_state(document)


# ---------------------------------------------------------------------------
# Ownership is an ID
# ---------------------------------------------------------------------------


def test_a_managed_client_secret_without_an_id_is_rejected() -> None:
    """Revocation acts on IDs. Without one it would fall back to a name lookup.

    A provider name is not unique and is not proof of ownership, which is how
    one project comes to revoke another project's credential.
    """
    document = make_state()
    document["active_client_secret_id"] = ""
    with pytest.raises(config.ManifestError):
        bootstrap_state.validate_state(document)


def test_every_provider_id_field_is_mandatory() -> None:
    for field in ("infisical_project_id", "runtime_identity_id", "runtime_client_id"):
        document = make_state()
        del document[field]
        with pytest.raises(config.ManifestError):
            bootstrap_state.validate_state(document)


def test_state_updated_before_it_was_created_is_rejected() -> None:
    document = make_state()
    document["updated_at"] = "2026-08-03T10:00:00Z"
    with pytest.raises(BootstrapStateError, match="not a record of what happened"):
        bootstrap_state.validate_state(document)


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def manifests() -> tuple[dict[str, Any], dict[str, Any]]:
    project = yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))
    host = host_config.load_host_manifest(REPO_ROOT / "host.example.yaml")
    return project, host


def test_provider_digest_is_stable(manifests: tuple[dict[str, Any], dict[str, Any]]) -> None:
    project, host = manifests
    first = bootstrap_state.provider_inputs_digest(project, host)
    second = bootstrap_state.provider_inputs_digest(copy.deepcopy(project), copy.deepcopy(host))
    assert first == second
    assert len(first) == 64


def test_an_unrelated_manifest_change_does_not_force_provider_churn(
    manifests: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """§4.10: the convergence key is provider-relevant inputs, not the manifest.

    Changing a domain creates no provider work. If it registered as drift, every
    ordinary edit would produce a plan full of changes an operator cannot explain
    -- and an unexplainable plan is one nobody reads.
    """
    project, host = manifests
    before = bootstrap_state.provider_inputs_digest(project, host)

    changed = copy.deepcopy(project)
    changed["project"]["domain"] = "something-else.test"
    changed["api"]["max_rows"] = 250
    changed["database"]["pool_size"] = 5

    assert bootstrap_state.provider_inputs_digest(changed, host) == before


@pytest.mark.parametrize(
    ("document", "dotted", "value"),
    [
        ("project", "project.slug", "different-slug"),
        ("project", "project.environment", "prod"),
        ("host", "infisical.environment_slug", "staging"),
        ("host", "infisical.runtime_folder", "/other"),
        ("host", "infisical.organization_slug", "other-team"),
    ],
)
def test_a_provider_relevant_change_does_force_convergence(
    manifests: tuple[dict[str, Any], dict[str, Any]], document: str, dotted: str, value: str
) -> None:
    project, host = manifests
    before = bootstrap_state.provider_inputs_digest(project, host)

    changed = copy.deepcopy(project if document == "project" else host)
    section, field = dotted.split(".")
    changed[section][field] = value

    after = (
        bootstrap_state.provider_inputs_digest(changed, host)
        if document == "project"
        else bootstrap_state.provider_inputs_digest(project, changed)
    )
    assert after != before, f"{dotted} changed without changing the convergence key"


def test_is_converged_compares_the_recorded_digest() -> None:
    document = make_state()
    assert bootstrap_state.is_converged(document, "b" * 64)
    assert not bootstrap_state.is_converged(document, "c" * 64)


# ---------------------------------------------------------------------------
# The repair condition
# ---------------------------------------------------------------------------


def test_missing_credential_files_are_reported_as_repair(tmp_path: Path) -> None:
    """§4.10: a missing local client secret is not an ordinary idempotent apply.

    The provider still holds a credential nobody can use. Creating another one
    silently leaks the first; revoking the first before validating a replacement
    leaves the project with none.
    """
    document = make_state()
    assert sorted(bootstrap_state.needs_credential_repair(document)) == [
        "client_id_path",
        "client_secret_path",
    ]

    present = tmp_path / "infisical-client-id"
    present.write_text("cli-0123456789\n", encoding="utf-8")
    document["credential_files"]["client_id_path"] = str(present)
    assert bootstrap_state.needs_credential_repair(document) == ["client_secret_path"]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_a_missing_state_file_is_named(tmp_path: Path) -> None:
    with pytest.raises(BootstrapStateError, match="bootstrap state is missing"):
        bootstrap_state.load_state(tmp_path / "absent.json")


def test_a_symlinked_state_file_is_refused(tmp_path: Path) -> None:
    """Runbook §7: scripts must refuse symlinked state paths."""
    real = tmp_path / "real.json"
    real.write_text(json.dumps(make_state()), encoding="utf-8")
    link = tmp_path / "bootstrap-state.json"
    link.symlink_to(real)
    with pytest.raises(BootstrapStateError, match="symlink"):
        bootstrap_state.load_state(link)


def test_malformed_json_is_named(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap-state.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BootstrapStateError, match="not valid JSON"):
        bootstrap_state.load_state(path)


def test_a_valid_file_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "bootstrap-state.json"
    path.write_text(json.dumps(make_state()), encoding="utf-8")
    assert bootstrap_state.load_state(path)["project_key"] == "alpha-dev"
