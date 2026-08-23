"""The backup identity plane, Session 10 Run 2.

Session 1 derived a stanza and a repository prefix and stopped there. This
module covers what Run 2 adds around them -- the repository's bucket, the egress
network, the retention bound that was declared and read by nothing (D519), and
what the manifest refuses -- plus the version 13 migrator's refusals.

What is deliberately NOT here: anything about pgBackRest itself. No config is
rendered until Run 4 and no repository is reached until the host trip. A module
that asserted the shape of a `pgbackrest.conf` this session has not written yet
would be a test of an intention.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, naming, output_migrations
from agentic_postgres.config import ManifestError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURES = REPO_ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# The derivations
# ---------------------------------------------------------------------------


def test_the_repository_bucket_is_namespaced_like_every_other_derived_name() -> None:
    """ADR 0105 applied to a second bucket, not restated for it.

    D339 found `storage_bucket_name` returning a bare project key into an
    account that already held six unrelated buckets. The repository is the one
    store here that cannot be recreated if its name collides, and R2 has no
    rename.
    """
    assert naming.backup_bucket_name("fixture-alpha-dev") == "apg-fixture-alpha-dev-backup"


def test_an_overridden_repository_bucket_is_used_verbatim() -> None:
    """The override exists so an operator can name a bucket our way or theirs.

    Prefixing it would defeat the only reason it exists (ADR 0105). The value
    here is deliberately not `apg-`-shaped: an override that happened to look
    derived would pass whether or not the prefixing branch was taken, which is
    D374's shape.
    """
    assert naming.backup_bucket_name("fixture-alpha-dev", "someone-elses-name") == (
        "someone-elses-name"
    )


def test_a_disabled_backup_names_no_repository() -> None:
    """A rendered document must not name a repository for a facility that is off.

    The stanza and the prefix have behaved this way since Session 1; the bucket
    joins them rather than being the one identity that is always present.
    """
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="alpha.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
        backup_enabled=False,
    )
    assert identity.backup_bucket is None
    assert identity.backup_stanza is None
    assert identity.backup_repository_prefix is None
    # The NETWORK is still derived, and the asymmetry is deliberate: Compose
    # refuses an empty value as firmly as an unset one (D178, ADR 0062), so a
    # project with backups off must still render a network name even though
    # nothing will attach to it. That is `storage_bucket_name`'s two-readers
    # problem, in the other direction.
    assert identity.backup_network == "apg-fixture-alpha-dev-backup"


def test_the_repository_bucket_cannot_collide_with_the_projects_own_storage_bucket() -> None:
    """The collision `ISOLATED_FIELDS` structurally cannot see.

    Every isolation proof in this repository compares two DIFFERENT projects.
    This one is within a single project, and it is reachable: both names are
    truncated to 63 characters, and for a long key the first 52 characters of
    `apg-{key}` and `apg-{key}-backup` are identical. What separates them is
    that `truncate` fingerprints the untruncated value AND the context, and both
    differ -- so this asserts the outcome rather than trusting the mechanism.
    """
    long_key = naming.project_key("a" * 60, "dev")
    storage = naming.storage_bucket_name(long_key)
    backup = naming.backup_bucket_name(long_key)

    assert len(storage) == naming.R2_BUCKET_MAX
    assert len(backup) == naming.R2_BUCKET_MAX
    assert storage[:52] == backup[:52], (
        "the premise of this test is gone: if the truncated stems no longer "
        "match, the collision it guards against is no longer reachable and the "
        "assertion below passes for a reason unrelated to fingerprinting"
    )
    assert storage != backup


def test_the_network_derivation_has_exactly_one_definition() -> None:
    """`derive` and `backup_network_name` are one derivation, not two spellings.

    The split exists because `output_migrations` is a third reader, and a
    migrator computing the name inline would be a second derivation of a name
    ADR 0002 allows one of.
    """
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="alpha.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    assert identity.backup_network == naming.backup_network_name(identity.key)


# ---------------------------------------------------------------------------
# What the manifest refuses
# ---------------------------------------------------------------------------


def _manifest(**backup: Any) -> dict[str, Any]:
    document = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    document["backup"] = {**document["backup"], **backup}
    return document


def test_an_enabled_backup_requires_an_account_id() -> None:
    """`_validate_storage`'s rule, applied to a second facility.

    The message has to name where the value comes from: a schema failure reads
    "'account_id' is a required property", which is true and tells an operator
    nothing about a value that exists only in a Cloudflare dashboard.
    """
    document = _manifest(account_id=None)
    with pytest.raises(ManifestError, match=r"backup\.account_id is required"):
        config.validate_project_semantics(document)


def test_a_disabled_backup_may_not_name_an_account_or_a_bucket() -> None:
    document = _manifest(
        enabled=False,
        stanza=None,
        repository_prefix=None,
        account_id="0123456789abcdef0123456789abcdef",
    )
    with pytest.raises(ManifestError, match="backup is disabled"):
        config.validate_project_semantics(document)


def test_a_malformed_account_id_is_refused_through_the_deriver() -> None:
    """One authority for what a well-formed account id is (ADR 0002).

    Re-checking the pattern in `config` would be a second copy that can drift
    from `naming`'s, so the refusal comes back out of `storage_endpoint_url`.
    """
    document = _manifest(account_id="not-32-hex")
    with pytest.raises(ManifestError, match="32 lowercase hex"):
        config.validate_project_semantics(document)


def test_a_malformed_repository_bucket_is_refused() -> None:
    document = _manifest(bucket="Not_A_Valid_Bucket")
    with pytest.raises(ManifestError, match="invalid R2 bucket name"):
        config.validate_project_semantics(document)


def test_the_example_manifests_between_them_render_both_bucket_paths() -> None:
    """One fixture derives its bucket and the other overrides it.

    Neither alone would exercise both branches, and two fixtures that made the
    same choice would leave one path rendered by nothing -- which is how
    `retain_full` reached Session 10 unread.
    """
    alpha = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    beta = config.load_project_manifest(REPO_ROOT / "project.second.example.yaml")

    assert alpha["backup"].get("bucket") is None, "the alpha fixture must exercise the derivation"
    assert beta["backup"]["bucket"] == "alpine-dev-repository"
    assert not beta["backup"]["bucket"].startswith("apg-"), (
        "an override that looked derived would pass whether or not the prefixing branch was taken"
    )


# ---------------------------------------------------------------------------
# The retention bound that was declared and read by nothing (D519)
# ---------------------------------------------------------------------------


def test_retain_full_has_a_default_and_it_matches_the_schema() -> None:
    """`config.BACKUP_DEFAULTS` and the schema's `default` are two statements.

    `test_budget_defaults_match_the_schema` exists for the same pairing on the
    database budget, for the same reason: JSON Schema's `default` annotates and
    does not enforce, so the two can disagree without anything noticing.
    """
    schema = config.load_schema("project.schema.json")
    declared = schema["properties"]["backup"]["properties"]["retain_full"]["default"]
    assert config.BACKUP_DEFAULTS["retain_full"] == declared


@pytest.mark.parametrize("value", [0, 13])
def test_retain_full_outside_the_schemas_bounds_is_refused(value: int) -> None:
    document = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    document["backup"]["retain_full"] = value
    with pytest.raises(ManifestError):
        config.validate_against_schema(document, "project.schema.json")


def test_retain_full_reaches_the_rendered_document(alpha_outputs: dict[str, Any]) -> None:
    """D519's actual repair, asserted where it can be seen.

    The bound was validated for nine sessions and reached no reader. This is the
    assertion that would have gone red the whole time.
    """
    assert alpha_outputs["backup"]["retain_full"] == 2


def test_retain_full_is_published_even_when_backups_are_disabled() -> None:
    """A bound is not a name.

    The three identities go null when the facility is off, because a rendered
    document must not name a repository that does not exist. `retain_full` stays,
    because nulling it would put "the default is two chains" back where only
    source can answer it.
    """
    document = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    document["backup"] = {"enabled": False}
    rendered = _render(document)
    assert rendered["backup"]["enabled"] is False
    assert rendered["backup"]["bucket"] is None
    assert rendered["backup"]["stanza"] is None
    assert rendered["backup"]["retain_full"] == config.BACKUP_DEFAULTS["retain_full"]


# ---------------------------------------------------------------------------
# The rendered document
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def alpha_outputs() -> dict[str, Any]:
    path = REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json"
    if not path.exists():
        pytest.skip("the alpha fixture has not been rendered")
    return json.loads(path.read_text(encoding="utf-8"))


def _render(document: dict[str, Any]) -> dict[str, Any]:
    """Render a manifest dict without touching `.generated/`.

    `render_project` publishes into `.generated/<key>`, and the Session 1 gate
    compares every rendered project there for identity collisions -- so a test
    that called it would have to delete what it published (CLAUDE.md §1). This
    reaches the pure function underneath instead.
    """
    from agentic_postgres import rendering

    capabilities_path = REPO_ROOT / "capabilities.example.yaml"
    capabilities = config.load_capabilities_manifest(capabilities_path)
    identity = naming.derive(
        slug=document["project"]["slug"],
        environment=document["project"]["environment"],
        domain=document["project"]["domain"],
        api_base_path=document["api"]["public_base_path"],
        mcp_base_path=document["mcp"]["public_base_path"],
        database_name=document["database"].get("name"),
        storage_enabled=bool((document.get("storage") or {}).get("enabled", False)),
        storage_bucket=(document.get("storage") or {}).get("bucket"),
        storage_prefix=(document.get("storage") or {}).get("prefix"),
        backup_enabled=bool((document.get("backup") or {}).get("enabled", False)),
        backup_stanza=(document.get("backup") or {}).get("stanza"),
        backup_repository_prefix=(document.get("backup") or {}).get("repository_prefix"),
        backup_bucket=(document.get("backup") or {}).get("bucket"),
    )
    digests = rendering.input_digests(
        REPO_ROOT / "project.example.yaml",
        capabilities_path,
    )
    return rendering.build_outputs(document, capabilities, identity, digests)


def test_the_rendered_document_names_the_repository_and_the_network(
    alpha_outputs: dict[str, Any],
) -> None:
    assert alpha_outputs["schema_version"] == 13
    assert alpha_outputs["backup"]["bucket"] == "apg-fixture-alpha-dev-backup"
    assert alpha_outputs["compose"]["networks"]["backup"] == "apg-fixture-alpha-dev-backup"


def test_the_repository_bucket_is_not_the_application_bucket(
    alpha_outputs: dict[str, Any],
) -> None:
    """ADR 0145's whole point, at the one place both names appear together."""
    assert alpha_outputs["backup"]["bucket"] != alpha_outputs["storage"]["bucket"]


# ---------------------------------------------------------------------------
# The version 13 migrator refuses rather than inventing
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v12() -> dict[str, Any]:
    """A genuine v12 rendered document, built by the chain from the v1 fixture.

    Not a hand-written dict: a fixture assembled here would agree with itself
    and with nothing else, and the point of these refusals is what they do to a
    document the migrator will really be handed.
    """
    import test_output_migrations as chain  # the module's own helpers

    v1 = json.loads((FIXTURES / "outputs-v1.json").read_text(encoding="utf-8"))
    document = output_migrations.migrate_v1_to_v2(v1, secrets_contract_sha256=chain.CONTRACT_DIGEST)
    document = output_migrations.migrate_v2_to_v3(
        document, database_budget=chain.BUDGET, database_container=chain.CONTAINER
    )
    document = output_migrations.migrate_v3_to_v4(
        document, access_profiles=chain.profiles_for(document)
    )
    document = output_migrations.migrate_v4_to_v5(document)
    document = output_migrations.migrate_v5_to_v6(
        document, documentation_role=chain.documentation_role_for(document)
    )
    document = output_migrations.migrate_v6_to_v7(
        document, statement_timeouts=chain.statement_timeouts_for(document)
    )
    document = output_migrations.migrate_v7_to_v8(
        document, api_connection_budget=chain.api_budget_for(document)
    )
    document = output_migrations.migrate_v8_to_v9(
        document, app_docs_url=chain.app_docs_url_for(document)
    )
    document = output_migrations.migrate_v9_to_v10(
        document, auth_connection_budget=chain.auth_budget_for(document)
    )
    document = output_migrations.migrate_v10_to_v11(
        document,
        storage_connection_budget=chain.storage_budget_for(document),
        pooler_pool_size=chain.pooler_pool_size_for(document),
        storage_route_url=chain.storage_route_url_for(document),
        storage_settings=chain.storage_settings_for(document),
    )
    return output_migrations.migrate_v11_to_v12(document)


def _v13(document: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "backup_bucket": naming.backup_bucket_name(document["project"]["key"]),
        "backup_retain_full": 2,
        "backup_network": naming.backup_network_name(document["project"]["key"]),
        **overrides,
    }
    return output_migrations.migrate_v12_to_v13(document, **arguments)


def test_the_v12_step_reaches_a_document_that_validates(v12: dict[str, Any]) -> None:
    assert v12["schema_version"] == 12
    migrated = _v13(v12)
    assert migrated["schema_version"] == 13
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_the_migrator_refuses_to_invent_a_bucket_for_an_enabled_repository(
    v12: dict[str, Any],
) -> None:
    """`migrate_v11_to_v12`'s refusal, applied to a name instead of a route.

    A migrator that computed `f"apg-{key}-backup"` would be a second derivation
    of a name ADR 0002 allows one of, arriving through the module that exists
    for documents whose inputs are gone.
    """
    assert v12["backup"]["enabled"] is True
    with pytest.raises(output_migrations.MigrationError, match="no backup_bucket was supplied"):
        _v13(v12, backup_bucket=None)


def test_the_migrator_refuses_a_bucket_for_a_disabled_repository(v12: dict[str, Any]) -> None:
    document = {**v12, "backup": {**v12["backup"], "enabled": False}}
    with pytest.raises(output_migrations.MigrationError, match="backups are disabled"):
        _v13(document)


def test_the_migrator_refuses_a_retention_outside_the_schemas_bounds(
    v12: dict[str, Any],
) -> None:
    with pytest.raises(output_migrations.MigrationError, match="between 1 and 12"):
        _v13(v12, backup_retain_full=13)


def test_the_migrator_refuses_a_document_that_already_names_a_backup_network(
    v12: dict[str, Any],
) -> None:
    once = _v13(v12)
    with pytest.raises(output_migrations.MigrationError, match="already version 13"):
        _v13(once)


def test_the_migrator_does_not_mutate_its_input(v12: dict[str, Any]) -> None:
    before = json.dumps(v12, sort_keys=True)
    _v13(v12)
    assert json.dumps(v12, sort_keys=True) == before
