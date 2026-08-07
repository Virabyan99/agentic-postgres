"""Secret requirements contract (Session 2, Phase 2).

This file declares the grant surface, so the tests are about *what cannot be
declared* far more than about what can. Three properties carry the design:

* a target filename cannot leave its generation directory;
* a source path is derived from the project key and cannot come from a manifest;
* the session filter keeps a later session's credential out of this session's
  Compose model.

No test here reads or constructs a secret value. The contract holds identifiers
only, and a test that needed a value would mean the contract did not.

The cross-check between a consumer's numeric UID and the Compose service's
``user:`` lands in Run 2, with the service.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, secrets_contract
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CONTRACT = REPO_ROOT / "secrets.required.yaml"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return secrets_contract.load_secret_contract(CONTRACT)


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def load_mutated(directory: Path, raw: dict[str, Any], mutate) -> dict[str, Any]:
    document = copy.deepcopy(raw)
    mutate(document)
    path = directory / "secrets.required.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return secrets_contract.load_secret_contract(path)


# ---------------------------------------------------------------------------
# The committed contract
# ---------------------------------------------------------------------------


def test_committed_contract_is_valid(contract: dict[str, Any]) -> None:
    assert contract["schema_version"] == 1


def test_contract_declares_no_secret_value(raw: dict[str, Any]) -> None:
    """Identifiers only. A value or a hash here would make the repo a vault."""
    config.assert_no_sensitive_keys(raw)


def test_session_two_declares_exactly_the_sentinel(contract: dict[str, Any]) -> None:
    """Session 2 materializes one secret, and it exists to be searched for.

    Keeping the Session 2 set at exactly one is what makes the leak scan a
    measurement: there is one known byte sequence, so a hit is unambiguous.
    """
    active = secrets_contract.active_secrets(contract, 2)
    assert [s["name"] for s in active] == ["session2_sentinel"]


def test_every_consumer_declares_non_root_numeric_ownership(contract: dict[str, Any]) -> None:
    for secret in contract["secrets"]:
        for consumer in secret["consumers"]:
            assert isinstance(consumer["uid"], int) and consumer["uid"] > 0
            assert isinstance(consumer["gid"], int) and consumer["gid"] > 0
            assert consumer["mode"] == "0400"


# ---------------------------------------------------------------------------
# Path derivation — the isolation property
# ---------------------------------------------------------------------------


def test_source_path_is_derived_from_the_project_key(contract: dict[str, Any]) -> None:
    """The project key is a path component, so it cannot be forged by a manifest."""
    consumer = contract["secrets"][0]["consumers"][0]
    path = secrets_contract.secret_source_path("alpha-dev", "gen-0001", consumer)
    assert path == (
        "/var/lib/agentic-postgres/secrets/alpha-dev/generations/gen-0001"
        "/secret-check/session2_sentinel"
    )


def test_two_projects_never_share_a_secret_path(contract: dict[str, Any]) -> None:
    consumer = contract["secrets"][0]["consumers"][0]
    alpha = secrets_contract.secret_source_path("alpha-dev", "gen-0001", consumer)
    beta = secrets_contract.secret_source_path("beta-dev", "gen-0001", consumer)
    assert alpha != beta
    assert "alpha-dev" not in beta and "beta-dev" not in alpha


def test_each_consumer_gets_its_own_directory(contract: dict[str, Any]) -> None:
    """Per-consumer, not per-secret.

    Two services sharing one file would need one set of permissions to satisfy
    two runtime users, and the usual resolution is to widen the mode. A separate
    file per consumer makes 'A cannot read B's copy' a filesystem property.
    """
    consumer = contract["secrets"][0]["consumers"][0]
    path = secrets_contract.secret_source_path("alpha-dev", "gen-0001", consumer)
    assert f"/{consumer['service']}/" in path


@pytest.mark.parametrize("target", ["../escape", "nested/file", "..", "/absolute"])
def test_a_target_filename_that_could_escape_is_rejected(
    tmp_path: Path, raw: dict[str, Any], target: str
) -> None:
    """The failure this contract exists to prevent."""

    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["consumers"][0]["target_file"] = target

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_a_wildcard_provider_path_is_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    """A wildcard path is a folder-wide export wearing a declaration's clothes."""

    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["provider_path"] = "/runtime/*"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------


def test_a_duplicate_provider_key_is_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    """Two local names for one provider key makes rotation ambiguous."""

    def mutate(document: dict[str, Any]) -> None:
        duplicate = copy.deepcopy(document["secrets"][0])
        duplicate["name"] = "session2_sentinel_copy"
        document["secrets"].append(duplicate)

    with pytest.raises(ManifestError, match="duplicate provider_key"):
        load_mutated(tmp_path, raw, mutate)


def test_a_duplicate_secret_name_is_rejected(tmp_path: Path, raw: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["secrets"].append(copy.deepcopy(document["secrets"][0]))
        document["secrets"][1]["provider_key"] = "APG_OTHER_KEY"

    with pytest.raises(ManifestError, match="duplicate secret name"):
        load_mutated(tmp_path, raw, mutate)


def test_one_service_may_not_receive_two_files_with_one_name(
    tmp_path: Path, raw: dict[str, Any]
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        secret = document["secrets"][0]
        secret["consumers"].append(copy.deepcopy(secret["consumers"][0]))

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_two_services_may_share_a_basename(tmp_path: Path, raw: dict[str, Any]) -> None:
    """Each gets its own directory, and each sees it at the same /run/secrets path."""

    def mutate(document: dict[str, Any]) -> None:
        secret = document["secrets"][0]
        second = copy.deepcopy(secret["consumers"][0])
        second["service"] = "other-service"
        secret["consumers"].append(second)

    document = load_mutated(tmp_path, raw, mutate)
    grants = document["secrets"][0]["consumers"]
    assert {c["service"] for c in grants} == {"secret-check", "other-service"}
    assert len({c["target_file"] for c in grants}) == 1


# ---------------------------------------------------------------------------
# Root ownership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["uid", "gid"])
def test_root_owned_secret_files_are_rejected(
    tmp_path: Path, raw: dict[str, Any], field: str
) -> None:
    """A root-owned file is unreadable by a container that drops privileges.

    The usual fix is to widen the mode, which is how 0400 becomes 0444.
    """

    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["consumers"][0][field] = 0

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


# ---------------------------------------------------------------------------
# The session filter
# ---------------------------------------------------------------------------


def test_a_later_session_secret_is_not_active_now(tmp_path: Path, raw: dict[str, Any]) -> None:
    """This is what lets Session 3 append without changing Session 2's grants."""

    def mutate(document: dict[str, Any]) -> None:
        later = copy.deepcopy(document["secrets"][0])
        later.update(name="db_password_ref", provider_key="APG_DB_CREDENTIAL")
        later["introduced_in_session"] = 3
        document["secrets"].append(later)

    document = load_mutated(tmp_path, raw, mutate)
    assert [s["name"] for s in secrets_contract.active_secrets(document, 2)] == [
        "session2_sentinel"
    ]
    # Membership, not a count. The count was 2 while Session 3 declared no
    # secrets of its own; now that it declares two, a length assertion has to be
    # edited every time the contract grows -- and the property under test was
    # never about how many there are. What matters is that the injected
    # session-3 secret appears at 3, does not appear at 2, and that the
    # session-2 set is exactly the secrets introduced by session 2 or earlier.
    at_two = {s["name"] for s in secrets_contract.active_secrets(document, 2)}
    at_three = {s["name"] for s in secrets_contract.active_secrets(document, 3)}
    assert "db_password_ref" in at_three
    assert "db_password_ref" not in at_two
    assert at_two < at_three, "session 2's grants must be a strict subset of session 3's"
    assert all(
        s["introduced_in_session"] <= 2 for s in secrets_contract.active_secrets(document, 2)
    )
    assert secrets_contract.granted_services(document, 2) == {"secret-check"}


def test_consumers_of_returns_only_that_services_grants(contract: dict[str, Any]) -> None:
    assert len(secrets_contract.consumers_of(contract, "secret-check", 2)) == 1
    assert secrets_contract.consumers_of(contract, "edge-probe", 2) == []


def test_the_edge_probe_receives_no_secret(contract: dict[str, Any]) -> None:
    """Runbook Phase 11: the public-facing container mounts nothing."""
    assert "edge-probe" not in secrets_contract.granted_services(contract, 2)


def test_container_path_is_the_compose_secrets_convention(contract: dict[str, Any]) -> None:
    consumer = contract["secrets"][0]["consumers"][0]
    assert secrets_contract.container_secret_path(consumer) == "/run/secrets/session2_sentinel"


# ---------------------------------------------------------------------------
# Cross-check against the Compose model (deferred from Run 1 with the service)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose_model() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_every_consumer_names_a_real_compose_service(
    contract: dict[str, Any], compose_model: dict[str, Any]
) -> None:
    """A grant to a service that does not exist is a grant nobody can audit."""
    services = set(compose_model["services"])
    for secret in contract["secrets"]:
        for consumer in secret["consumers"]:
            assert consumer["service"] in services, (
                f"secret {secret['name']!r} is granted to {consumer['service']!r}, "
                f"which is not a service in compose.yaml"
            )


def test_consumer_ownership_matches_the_service_runtime_user(
    contract: dict[str, Any], compose_model: dict[str, Any]
) -> None:
    """The two numbers live in two files, which is how they come to disagree.

    The host sets ownership on a secret file *before* Compose mounts it -- ADR
    0010 deliberately does not rely on Compose's own uid/gid/mode fields. So if
    the declared consumer UID and the service's `user:` diverge, the container
    gets a file it cannot read, and the usual fix is to widen the mode from 0400.
    """
    for secret in contract["secrets"]:
        for consumer in secret["consumers"]:
            service = compose_model["services"][consumer["service"]]
            expected = f"{consumer['uid']}:{consumer['gid']}"
            assert service.get("user") == expected, (
                f"{consumer['service']} runs as {service.get('user')!r} but secret "
                f"{secret['name']!r} is materialized owned by {expected}"
            )


def test_no_service_receives_a_secret_it_was_not_granted(
    contract: dict[str, Any], compose_model: dict[str, Any]
) -> None:
    """SEC-SECRET-002, checked from source.

    The committed model declares no `secrets:` block at all -- the generation
    path does not exist until materialization runs -- so the assertion is that
    every service's grant list is empty here. The runtime override adds exactly
    the declared grants, and the live suite asserts the mount list inside the
    running container.
    """
    granted = secrets_contract.granted_services(contract, 2)
    for name, service in compose_model["services"].items():
        assert "secrets" not in service, (
            f"service {name} declares a secret grant in the committed model; "
            "grants belong in the root-owned runtime override"
        )
    assert granted == {"secret-check"}


def test_the_publicly_routed_service_is_granted_nothing(
    contract: dict[str, Any], compose_model: dict[str, Any]
) -> None:
    """The one container reachable from the Internet holds no secret material."""
    assert "edge-probe" in compose_model["services"]
    assert "edge-probe" not in secrets_contract.granted_services(contract, 2)
