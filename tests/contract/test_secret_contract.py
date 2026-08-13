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


def test_every_compose_consumer_declares_non_root_numeric_ownership(
    contract: dict[str, Any],
) -> None:
    for secret in contract["secrets"]:
        for consumer in secrets_contract.compose_consumers(secret):
            assert isinstance(consumer["uid"], int) and consumer["uid"] > 0
            assert isinstance(consumer["gid"], int) and consumer["gid"] > 0
            assert consumer["mode"] == "0400"


def test_every_root_plane_consumer_is_owned_by_root_and_names_no_service(
    contract: dict[str, Any],
) -> None:
    """The rule that is the exact opposite of the one above (ADR 0054).

    On the compose plane root ownership is refused, because a container that
    drops privileges could not read the file. On this plane it is required, for
    the reason the plane exists: a file any other uid can read is a file that a
    value no container may hold must not be.
    """
    root_plane = [
        consumer
        for secret in contract["secrets"]
        for consumer in secret["consumers"]
        if secrets_contract.is_root_plane(consumer)
    ]
    assert root_plane, "no root-plane consumer is declared; this test asserts nothing"
    for consumer in root_plane:
        assert (consumer["uid"], consumer["gid"]) == (0, 0)
        assert consumer["mode"] == "0400"
        assert "service" not in consumer


def test_every_secret_declares_what_kind_of_value_it_is(contract: dict[str, Any]) -> None:
    """ADR 0055. A default here is how the wrong generator runs.

    The set is asserted against the schema's enum rather than a list written
    here, so a new kind added to one and not the other fails rather than passing
    on the copy that happens to be read.
    """
    schema = config.load_schema("secret-contract.schema.json")
    kinds = set(schema["$defs"]["secret"]["properties"]["value_kind"]["enum"])
    for secret in contract["secrets"]:
        assert secret["value_kind"] in kinds, secret["name"]
    assert {s["value_kind"] for s in contract["secrets"]} == kinds, (
        "a declared kind that nothing uses is a generator branch nothing exercises"
    )


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
# The root plane (ADR 0054)
# ---------------------------------------------------------------------------


def root_consumer(**overrides: Any) -> dict[str, Any]:
    return {
        "plane": "root",
        "target_file": "held_by_root_only",
        "uid": 0,
        "gid": 0,
        "mode": "0400",
        **overrides,
    }


def test_a_root_plane_file_lands_in_a_directory_no_service_can_name(
    contract: dict[str, Any],
) -> None:
    """`_root` is unreachable by construction, not by convention.

    The Compose service pattern admits no underscore, so no service can be
    called `_root` and no service's directory can collide with this one. The
    assertion is on the pattern as well as on the path, because the path is only
    safe for as long as that pattern is.
    """
    consumer = root_consumer()
    path = secrets_contract.secret_source_path("alpha-dev", "gen-0001", consumer)
    assert path.endswith("/generations/gen-0001/_root/held_by_root_only")

    schema = config.load_schema("secret-contract.schema.json")
    pattern = schema["$defs"]["composeConsumer"]["properties"]["service"]["pattern"]
    import re

    assert not re.match(pattern, secrets_contract.ROOT_PLANE_DIRECTORY)


def test_a_root_plane_consumer_is_no_service_grant(contract: dict[str, Any]) -> None:
    """It is invisible to every function that answers "what does a container get"."""
    signing = next(s for s in contract["secrets"] if s["name"] == "bootstrap_jwt_signing_key")
    assert secrets_contract.compose_consumers(signing) == []
    assert "bootstrap_jwt_signing_key" not in {
        grant["secret"]["name"]
        for service in secrets_contract.granted_services(contract, 5)
        for grant in secrets_contract.consumers_of(contract, service, 5)
    }


def test_a_root_plane_consumer_reaches_no_compose_override(contract: dict[str, Any]) -> None:
    """The absence, asserted rather than trusted.

    A root-plane consumer produces no `secrets:` entry, no service grant and no
    mount. It gets them by not being iterated, so the thing worth checking is
    that its target filename appears nowhere in the rendered override.
    """
    from agentic_postgres import secret_override

    document = secret_override.build_secret_override(
        project_key="alpha-dev", generation_id="gen0001x", contract=contract, session=5
    )
    rendered = yaml.safe_dump(document)
    assert "bootstrap_jwt_signing_key" not in rendered
    assert "docs_basic_auth_password" not in rendered
    assert "_root" not in rendered


@pytest.mark.parametrize(("field", "value"), [("uid", 65532), ("gid", 65532)])
def test_a_root_plane_consumer_owned_by_anyone_else_is_refused(
    tmp_path: Path, raw: dict[str, Any], field: str, value: int
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        secret = next(s for s in document["secrets"] if s["name"] == "bootstrap_jwt_signing_key")
        secret["consumers"][0][field] = value

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_a_root_plane_consumer_may_not_name_a_service(tmp_path: Path, raw: dict[str, Any]) -> None:
    """The two planes are separate definitions, not one loosened definition.

    A consumer that named a service *and* claimed the root plane would be a
    grant with two readings, and the reading a renderer picked would decide
    whether a private key got mounted.
    """

    def mutate(document: dict[str, Any]) -> None:
        secret = next(s for s in document["secrets"] if s["name"] == "bootstrap_jwt_signing_key")
        secret["consumers"][0]["service"] = "postgrest"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_a_consumer_with_no_plane_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    """Required on every consumer, including the ones that predate the field."""

    def mutate(document: dict[str, Any]) -> None:
        del document["secrets"][0]["consumers"][0]["plane"]

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_a_secret_with_no_value_kind_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    """ADR 0055: a default is how a hex string ends up stored under a key's name."""

    def mutate(document: dict[str, Any]) -> None:
        del document["secrets"][0]["value_kind"]

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_an_unknown_value_kind_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["value_kind"] = "ed25519_private_pem"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_the_signing_key_is_declared_as_a_key_and_not_as_a_password(
    contract: dict[str, Any],
) -> None:
    """The declaration ADR 0055 exists to make possible.

    Without `value_kind` the generator would write 32 bytes of hex here, the
    contract would validate, the file would be materialized at 0400 root, the
    manifest would record it, and the failure would arrive several runs later as
    a JWKS derived from something that is not a key.
    """
    signing = next(s for s in contract["secrets"] if s["name"] == "bootstrap_jwt_signing_key")
    assert signing["value_kind"] == "rsa_private_pem"
    assert signing["consumers"][0]["plane"] == "root"
    assert signing["provider_path"] == "/auth"


def test_the_documentation_credential_reaches_no_container(contract: dict[str, Any]) -> None:
    """D140's answer, asserted where it can be.

    The container that serves the documentation must never hold the cleartext --
    that is the entire point of stripping the header before the request reaches
    it -- and the edge that checks it is not a project Compose service. So the
    credential is on the root plane, and no service name appears anywhere near
    it.
    """
    credential = next(s for s in contract["secrets"] if s["name"] == "docs_basic_auth_password")
    assert secrets_contract.compose_consumers(credential) == []
    assert credential["consumers"][0]["plane"] == "root"


# ---------------------------------------------------------------------------
# The format a consumer's file is written in (ADR 0056)
# ---------------------------------------------------------------------------


def test_raw_is_the_identity(contract: dict[str, Any]) -> None:
    """Every consumer but one gets the provider's bytes, unchanged."""
    consumer = contract["secrets"][0]["consumers"][0]
    assert consumer["format"] == "raw"
    assert secrets_contract.render_secret("a-value", consumer) == "a-value"


def test_pgpass_wraps_the_value_in_a_wildcard_line(contract: dict[str, Any]) -> None:
    """Wildcards in all four match fields, and that is the decision.

    Naming the host, port, database and role would put four derived identifiers
    inside a materialized secret -- a second derivation path for names naming.py
    owns, and a file that goes stale when any of them changes. The symptom then
    is `fe_sendauth: no password supplied`, which sends the reader to the wrong
    file entirely.
    """
    secret = next(s for s in contract["secrets"] if s["name"] == "postgrest_authenticator_password")
    consumer = secret["consumers"][0]
    assert secrets_contract.render_secret("hunter2", consumer) == "*:*:*:*:hunter2\n"


def test_a_value_with_a_line_break_is_refused_in_pgpass_format(
    contract: dict[str, Any],
) -> None:
    """It would end the line and leave the remainder as a malformed second entry.

    libpq skips a malformed line silently, so the failure would be a connection
    refused for a reason nothing states. The generator produces hex, so a value
    with a newline in it is a provider that returned something nobody declared.
    """
    secret = next(s for s in contract["secrets"] if s["name"] == "postgrest_authenticator_password")
    with pytest.raises(ManifestError, match="line break"):
        secrets_contract.render_secret("first\nsecond", secret["consumers"][0])


def test_the_pgpass_line_contains_only_the_value(contract: dict[str, Any]) -> None:
    """Guard the guard: no host, no port, no database, no role.

    Asserted against the derived names of a real project, so a template that
    started interpolating one would fail here rather than in a connection.
    """
    from agentic_postgres import naming

    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    secret = next(s for s in contract["secrets"] if s["name"] == "postgrest_authenticator_password")
    line = secrets_contract.render_secret("hunter2", secret["consumers"][0])
    for name in (identity.database_name, identity.roles["postgrest_authenticator"], "5432"):
        assert name not in line, name


def test_every_consumer_declares_a_format(contract: dict[str, Any]) -> None:
    formats = {c["format"] for s in contract["secrets"] for c in s["consumers"]}
    assert formats <= set(secrets_contract.FORMATS)
    assert formats == set(secrets_contract.FORMATS), (
        "a declared format that nothing uses is a writer nothing exercises"
    )


# ---------------------------------------------------------------------------
# Reading a materialized file back (Session 5 Run 5)
# ---------------------------------------------------------------------------


def test_every_format_round_trips(contract: dict[str, Any]) -> None:
    """The bootstrap plane needs the value, not the wrapper around it.

    `ALTER ROLE … PASSWORD` takes a password, and the API's authenticator
    credential is materialized as a pgpass line because the service that mounts
    it has no shell to unwrap one. So the pair has to be exact, for every format
    and not only the one that motivated it: a reader that quietly handed back
    `*:*:*:*:hunter2` would set the role's password to a string containing the
    password, and every subsequent connection would fail authentication with a
    file on disk that looks correct.
    """
    value = "b8f0a3c1d2e4f5a6"
    for secret in contract["secrets"]:
        for consumer in secret["consumers"]:
            rendered = secrets_contract.render_secret(value, consumer)
            recovered = secrets_contract.recover_secret(rendered, consumer)
            assert recovered == value, f"{secret['name']} / {consumer['format']}"


def test_a_pgpass_file_written_by_something_else_is_refused() -> None:
    """A file that does not begin with the template's prefix means the
    materializer did not write it, and what the rest of it means is unknown."""
    consumer = {"format": "pgpass"}
    with pytest.raises(ManifestError, match="does not begin with"):
        secrets_contract.recover_secret("localhost:5432:db:role:hunter2\n", consumer)


def test_a_format_with_no_reader_is_refused() -> None:
    """The realistic failure is a third format that only the writer learns about.

    Both halves raise on an unknown name so the pair fails loudly, rather than
    the reader passing a wrapper through as though it were a value.
    """
    with pytest.raises(ManifestError, match="no reader"):
        secrets_contract.recover_secret("anything", {"format": "base64"})
    with pytest.raises(ManifestError, match="no writer"):
        secrets_contract.render_secret("anything", {"format": "base64"})


def test_a_consumer_with_no_format_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        del document["secrets"][0]["consumers"][0]["format"]

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_an_unknown_format_is_refused(tmp_path: Path, raw: dict[str, Any]) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["secrets"][0]["consumers"][0]["format"] = "dotenv"

    with pytest.raises(ManifestError):
        load_mutated(tmp_path, raw, mutate)


def test_a_pgpass_file_may_not_hold_a_key(tmp_path: Path, raw: dict[str, Any]) -> None:
    """A password file holds a password.

    Refused at contract load rather than at the first failed connection, where
    the message would be `fe_sendauth` and the file would look plausible.
    """

    def mutate(document: dict[str, Any]) -> None:
        secret = next(s for s in document["secrets"] if s["name"] == "bootstrap_jwt_signing_key")
        secret["consumers"][0]["format"] = "pgpass"

    with pytest.raises(ManifestError, match="password file holds a password"):
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
        for consumer in secrets_contract.compose_consumers(secret):
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
        for consumer in secrets_contract.compose_consumers(secret):
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


# ---------------------------------------------------------------------------
# Naming a secret rather than a file (ADR 0075)
# ---------------------------------------------------------------------------


def test_a_consumer_is_resolved_by_secret_name_not_by_filename(
    contract: dict[str, Any],
) -> None:
    """``consumer_named`` maps (secret, holder) to the file, so no caller spells one.

    The authenticator is the case that made this a decision rather than a
    convenience: the secret is ``postgrest_authenticator_password`` and the file
    is ``postgrest_authenticator_pgpass``. A caller that knew only the pattern
    "filename equals secret name" -- true for every other entry in this contract
    -- names a path that does not exist.
    """
    secret, consumer = secrets_contract.consumer_named(
        contract, "postgrest_authenticator_password", "postgrest"
    )
    assert secret["name"] == "postgrest_authenticator_password"
    assert consumer["target_file"] == "postgrest_authenticator_pgpass"
    assert consumer["format"] == "pgpass"

    # The control: an entry where the two DO coincide still resolves, so the
    # assertion above is about this consumer and not about the lookup failing.
    _, raw = secrets_contract.consumer_named(contract, "app_runtime_password", "pgbouncer")
    assert raw["target_file"] == "app_runtime_password"
    assert raw["format"] == "raw"


def test_a_root_plane_consumer_is_reached_by_its_directory(contract: dict[str, Any]) -> None:
    """``_root`` is a holder like any other, and the only one no container names."""
    _, consumer = secrets_contract.consumer_named(
        contract, "docs_basic_auth_password", secrets_contract.ROOT_PLANE_DIRECTORY
    )
    assert secrets_contract.is_root_plane(consumer)
    assert "service" not in consumer


def test_an_undeclared_secret_or_holder_raises_rather_than_returning_nothing(
    contract: dict[str, Any],
) -> None:
    """A soft miss would read as "this secret is not held here", which is a claim.

    Both messages name identifiers only -- the secret's declared holders, and the
    contract's declared names -- because this function is called from tests that
    run as root beside real generation directories.
    """
    with pytest.raises(ManifestError, match="no secret named"):
        secrets_contract.consumer_named(contract, "postgrest_authenticator_pgpass", "postgrest")

    with pytest.raises(ManifestError, match="declares no consumer"):
        secrets_contract.consumer_named(contract, "docs_basic_auth_password", "postgrest")


def test_every_declared_consumer_round_trips_through_its_own_format(
    contract: dict[str, Any],
) -> None:
    """What ``materialized_secret`` now relies on, for every consumer in the file.

    The fixture reads a file and returns ``recover_secret(...)`` of it, so a
    consumer whose format did not round-trip would hand a test a value that is
    not the provider's -- and the test would then compare it against one that is.
    """
    value = "0123456789abcdef0123456789abcdef"
    for secret in contract["secrets"]:
        for consumer in secret["consumers"]:
            rendered = secrets_contract.render_secret(value, consumer)
            assert secrets_contract.recover_secret(rendered, consumer) == value, (
                f"{secret['name']} for {secrets_contract.consumer_directory(consumer)} does not "
                f"round-trip through format {consumer['format']!r}"
            )
            # As it lands on disk: the materializer writes a trailing newline and
            # every reader strips one.
            assert secrets_contract.recover_secret(rendered + "\n", consumer) == value


def test_a_secret_with_many_holders_resolves_to_the_one_asked_for(
    contract: dict[str, Any],
) -> None:
    """The discriminating case, and the reason the two above are not enough.

    Every secret this contract declares with a `pgpass` format, and both
    root-plane secrets, have exactly **one** consumer -- so a resolver that
    ignored the holder entirely and returned the first would satisfy them.
    ``app_runtime_password`` has five, and two of them differ in the number that
    decides whether the file is readable at all: the pooler runs as 70 and every
    client fixture as 65532.
    """
    _, pooler = secrets_contract.consumer_named(contract, "app_runtime_password", "pgbouncer")
    _, client = secrets_contract.consumer_named(contract, "app_runtime_password", "client-psql")

    assert pooler["service"] == "pgbouncer"
    assert client["service"] == "client-psql"
    assert (pooler["uid"], pooler["gid"]) == (70, 70)
    assert (client["uid"], client["gid"]) == (65532, 65532)
    assert pooler is not client
