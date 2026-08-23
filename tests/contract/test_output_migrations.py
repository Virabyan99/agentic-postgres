"""Output schema migration and document-kind rejection (ADR 0012, 0027, 0041, 0053).

All four fixtures are real renders, not hand-built objects: ``outputs-v1.json``
is a Session 1 render, ``outputs-v2.json`` a Session 2 one, ``outputs-v3.json``
a Session 3 one, and ``outputs-v4.json`` the Session 4 render every deployed
host is running at the time version 5 was written. A hand-built fixture drifts
away from what was actually shipped, and then the migrator is proved to handle a
document that never existed.

Two negative properties carry more weight here than the positive one:

* the migrator refuses to invent a ``deployed`` document, because every field
  that distinguishes one is an observation;
* a rendered document is refused where deployed state is required, and the
  refusal happens at the boundary rather than as a ``KeyError`` further in.
  The two files share a basename, so passing the wrong path is the realistic
  mistake.

The v3 step adds a third: it refuses to *derive* anything. `database.budget`
comes from a manifest and `database.container` from ``naming``, and this module
holds neither, so both are supplied by the caller and shape-checked.

The v4 step is the interesting one, because there it *could* derive. A profile's
transport is fixed by its name and its role is already in ``database.roles``, so
a migrator could fill both in and be right. It validates instead — a supplied
profile naming a role the document does not declare is refused rather than
corrected — because deriving would make this module a second authority on which
role serves which profile, and ADR 0002 allows one derivation path per name.

The v5 step is the opposite kind of interesting: it adds nothing at all, because
everything version 5 added is on the deployed branch. What is asserted about it
is therefore mostly what it still refuses — a deployed document, an incomplete
one, one carrying fields no v4 rendered document has — because a step that
changes one integer is exactly the one somebody would later be tempted to make a
shortcut past the checks.

The v6 step returns to the v3 shape and repeats its refusal for a fourth time.
It adds `database.roles.api_documentation` (D158), which *is* derivable — it is
``naming.database_role(sql_key, "api_documentation")`` — and is supplied by the
caller anyway, because deriving it here would make this module a second
authority on a derived identity. What it adds on top of the v3 pattern is a
collision check: two role keys naming one role is a document in which a grant
cannot be attributed to the role it was written for.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, config, naming, output_migrations
from agentic_postgres.output_migrations import MigrationError

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE_V1 = REPO_ROOT / "tests" / "fixtures" / "outputs-v1.json"
FIXTURE_V2 = REPO_ROOT / "tests" / "fixtures" / "outputs-v2.json"
FIXTURE_V3 = REPO_ROOT / "tests" / "fixtures" / "outputs-v3.json"
FIXTURE_V4 = REPO_ROOT / "tests" / "fixtures" / "outputs-v4.json"

#: The Session 5 render, produced by `deploy.sh --render-only` at commit
#: `8f2687d` -- Run 7 part one, the last commit that still rendered version 5.
#: Rendered rather than hand-made from `outputs-v4.json`, for the reason every
#: fixture here is: a document derived from the migrator is a document that
#: agrees with the migrator by construction.
FIXTURE_V5 = REPO_ROOT / "tests" / "fixtures" / "outputs-v5.json"

CONTRACT_DIGEST = sha256((REPO_ROOT / "secrets.required.yaml").read_bytes()).hexdigest()

#: What a caller supplies for the v3 step. Taken from the real resolver rather
#: than written out, so a change to the budget's shape fails here rather than
#: producing a fixture that agrees only with itself.
BUDGET = config.database_budget({})
CONTAINER = "apg-fixture-alpha-dev-postgres-1"


def profiles_for(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """What a caller supplies for the v4 step (ADR 0041).

    Built from the document's *own* declared roles rather than written out as
    literals, for the same reason ``BUDGET`` comes from the real resolver: a
    literal role name here would agree only with itself, and would keep agreeing
    after ``naming`` changed.

    Every profile is ``unavailable`` with a null secret reference, which is the
    only thing a migration may produce. An archived document records no bound
    port and no provisioned credential, so a profile claiming otherwise would be
    a deployment invented by a migrator.
    """
    roles = document["database"]["roles"]
    return {
        name: {
            "status": "unavailable",
            "available_from_session": 4,
            "transport": transport,
            "role": roles["migration_user" if name == "migration_direct" else "app_runtime"],
            "password_secret_ref": None,
        }
        for name, transport in output_migrations.ACCESS_PROFILE_TRANSPORTS.items()
    }


@pytest.fixture
def v1() -> dict[str, Any]:
    return json.loads(FIXTURE_V1.read_text(encoding="utf-8"))


@pytest.fixture
def v2_fixture() -> dict[str, Any]:
    """The committed Session 2 render."""
    return json.loads(FIXTURE_V2.read_text(encoding="utf-8"))


@pytest.fixture
def v3_fixture() -> dict[str, Any]:
    """The committed Session 3 render."""
    return json.loads(FIXTURE_V3.read_text(encoding="utf-8"))


@pytest.fixture
def v2(v1: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced one step."""
    return output_migrations.migrate_v1_to_v2(v1, secrets_contract_sha256=CONTRACT_DIGEST)


@pytest.fixture
def v3(v2: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced two steps, stopping at 3."""
    return output_migrations.migrate_v2_to_v3(
        v2, database_budget=BUDGET, database_container=CONTAINER
    )


@pytest.fixture
def v4_fixture() -> dict[str, Any]:
    """The committed Session 4 render."""
    return json.loads(FIXTURE_V4.read_text(encoding="utf-8"))


@pytest.fixture
def v4(v3: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced three steps, stopping at 4."""
    return output_migrations.migrate_v3_to_v4(v3, access_profiles=profiles_for(v3))


@pytest.fixture
def v5_fixture() -> dict[str, Any]:
    """The committed Session 5 render."""
    return json.loads(FIXTURE_V5.read_text(encoding="utf-8"))


@pytest.fixture
def v5(v4: dict[str, Any]) -> dict[str, Any]:
    """The v1 fixture advanced four steps, stopping at 5."""
    return output_migrations.migrate_v4_to_v5(v4)


def statement_timeouts_for(document: dict[str, Any]) -> dict[str, str]:
    """What version 7 requires, derived from the document under test.

    Keyed by derived role name, as the schema requires. Only `app_runtime` is
    named, because that is the platform default `rendering` always writes; a
    manifest's own entries are exercised in `test_output_schema.py`, which
    renders a manifest and can read them back out of the document.
    """
    return {document["database"]["roles"]["app_runtime"]: "30s"}


def auth_budget_for(document: dict[str, Any]) -> int:
    """What version 10 requires, from `config` rather than written out.

    `config.auth_connection_budget` is the one place that figure is computed,
    and the manifest-side budget check reasons about the same call. A literal
    here would agree with it today and diverge on the day one of them moved --
    which is the only day it would matter.
    """
    del document
    return config.auth_connection_budget({})


def app_docs_url_for(document: dict[str, Any]) -> str:
    """What version 9 requires, derived through `naming` from the document.

    Written out nowhere. `naming.DOCS_APP_PAGE_PATH` is the one authority for
    the path (ADR 0061) and the domain comes from the document under test, so
    a change to either fails here rather than producing a fixture that agrees
    only with itself.
    """
    return f"https://{document['project']['domain']}{naming.DOCS_APP_PAGE_PATH}"


def api_budget_for(document: dict[str, Any]) -> int:
    """What version 8 requires, from `config` rather than written out.

    `config.postgrest_connection_budget` is the one place that figure is
    computed, and the manifest-side budget check reasons about the same call. A
    literal here would agree with it today and diverge on the day one of them
    moved -- which is the only day it would matter.
    """
    del document
    return config.postgrest_connection_budget({})


def storage_budget_for(document: dict[str, Any]) -> int:
    """What version 11 requires, from `config` rather than written out.

    The same shape as the two functions above and for the same reason:
    `config.storage_connection_budget` is the one place that figure is computed
    (ADR 0099), and a literal here would agree with it today.
    """
    del document
    return config.storage_connection_budget({})


def pooler_pool_size_for(document: dict[str, Any]) -> int:
    """The pooler's server-side pool, from the example manifest.

    `database.pool_size` has no schema default -- it is required, so every
    manifest states it -- and an archived document is exactly a document that
    came from a manifest. Reading the repository's own rather than writing a
    literal keeps this fixture tied to a value somebody chose, and moves with it.
    """
    del document
    manifest = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    return int(manifest["database"]["pool_size"])


def storage_route_url_for(document: dict[str, Any]) -> str:
    """What version 11 requires, derived through `naming` from the document.

    Written out nowhere, exactly as `app_docs_url_for` is not: the path suffixes
    are `naming`'s single authority (ADR 0061, ADR 0002) and the domain and base
    path come from the document under test, so a change to either fails here
    rather than producing a fixture that agrees only with itself.
    """
    domain = document["project"]["domain"]
    # The published REST URL carries the manifest's own `api.public_base_path`,
    # which this document records nowhere else. Recovering it from the rendered
    # route is what keeps the fixture independent of the example manifest.
    base_path = (
        document["routes"]["rest"]
        .removeprefix(f"https://{domain}")
        .removesuffix(naming.REST_PATH_SUFFIX)
    )
    return f"https://{domain}{base_path}{naming.APP_PATH_SUFFIX}{naming.STORAGE_PATH_SUFFIX}"


def storage_settings_for(document: dict[str, Any]) -> dict[str, Any]:
    """What version 11 resolves into the storage block.

    From `config.STORAGE_DEFAULTS` rather than written out: those are the values
    a manifest that names none of them resolves to, and an archived document is
    exactly a document whose manifest named none of them. Supplying literals
    would be inventing an operator's choices.
    """
    del document
    return {name: config.STORAGE_DEFAULTS[name] for name in output_migrations._V11_STORAGE_MEMBERS}


def backup_bucket_for(document: dict[str, Any]) -> str | None:
    """What version 13 resolves into ``backup.bucket``.

    Derived through `naming` from the document's own project key, like every
    other helper here, and ``None`` when the archived document has backups off:
    the migrator refuses a bucket for a disabled facility, and supplying one
    would be testing a state the renderer cannot produce.

    A v12 document does not record whether its manifest overrode the bucket, so
    this resolves to the DERIVED name. That is `storage_settings_for`'s
    assumption, stated for the same reason -- an archived document is exactly a
    document whose manifest named none of these, and inventing an operator's
    override would be worse than assuming they made none.
    """
    backup = document.get("backup", {})
    if not backup.get("enabled"):
        return None
    return naming.backup_bucket_name(document["project"]["key"])


def backup_network_for(document: dict[str, Any]) -> str:
    """What version 13 resolves into ``compose.networks.backup``.

    Through `naming.backup_network_name`, which exists precisely so that this
    call and `derive`'s are one derivation rather than two spellings of it.
    """
    return naming.backup_network_name(document["project"]["key"])


def backup_retain_full_for(document: dict[str, Any]) -> int:
    """What version 13 resolves into ``backup.retain_full``.

    From `config.BACKUP_DEFAULTS` rather than the literal 2, for
    `storage_settings_for`'s reason: it is what a manifest naming nothing
    resolves to, and a literal here would keep agreeing with itself after the
    default moved.
    """
    del document
    return int(config.BACKUP_DEFAULTS["retain_full"])


def documentation_role_for(document: dict[str, Any]) -> str:
    """What a caller supplies for the v6 step (D158).

    Derived through `naming` from the document's *own* project key, not written
    out, for the reason `profiles_for` is built the same way: a literal role name
    would agree only with itself and would keep agreeing after `naming` changed.

    This is also the argument's whole justification. The name is derivable, and
    `output_migrations` deliberately does not derive it -- ADR 0002 allows one
    derivation path per name, and a migrator that computed role names would be a
    second one.
    """
    return naming.database_role(naming.sql_key(document["project"]["key"]), "api_documentation")


@pytest.fixture
def v6_document(v5_fixture: dict[str, Any]) -> dict[str, Any]:
    """The committed Session 5 render advanced to 6 -- the v7 step's input.

    Built from the fixture rather than from the chain so that a fault in an
    earlier step surfaces in that step's tests instead of here.
    """
    return output_migrations.migrate_v5_to_v6(
        v5_fixture, documentation_role=documentation_role_for(v5_fixture)
    )


@pytest.fixture
def chained(v1: dict[str, Any]) -> dict[str, Any]:
    """The whole chain, v1 -> ... -> the current version, through the public entry point.

    Named for what it is rather than for a version. It was called `v6` until
    version 7 arrived, at which point the name said 6 and the document said 7 --
    a fixture that reads as measured and is not, which is the defect this
    project keeps producing.
    """
    return output_migrations.migrate_rendered(
        v1,
        secrets_contract_sha256=CONTRACT_DIGEST,
        database_budget=BUDGET,
        database_container=CONTAINER,
        access_profiles=profiles_for(v1),
        documentation_role=documentation_role_for(v1),
        statement_timeouts=statement_timeouts_for(v1),
        api_connection_budget=api_budget_for(v1),
        app_docs_url=app_docs_url_for(v1),
        auth_connection_budget=auth_budget_for(v1),
        storage_connection_budget=storage_budget_for(v1),
        pooler_pool_size=pooler_pool_size_for(v1),
        storage_route_url=storage_route_url_for(v1),
        storage_settings=storage_settings_for(v1),
        backup_bucket=backup_bucket_for(v1),
        backup_retain_full=backup_retain_full_for(v1),
        backup_network=backup_network_for(v1),
    )


# ---------------------------------------------------------------------------
# The fixtures are genuine documents of their stated versions
# ---------------------------------------------------------------------------


def test_v1_fixture_is_version_one_and_no_longer_validates(v1: dict[str, Any]) -> None:
    """A v1 document must fail the current schema, or the migration is decorative."""
    assert output_migrations.detect_version(v1) == 1
    assert "document_kind" not in v1
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v1, "outputs.schema.json")


def test_v2_fixture_is_version_two_and_no_longer_validates(v2_fixture: dict[str, Any]) -> None:
    """The same claim for v2, which is the version deployed hosts are running.

    This is the test that makes the version bump mean something. If a v2
    document still validated, ``schema_version`` would be a label rather than a
    contract and an old reader would have no way to tell it was out of date.
    """
    assert output_migrations.detect_version(v2_fixture) == 2
    assert v2_fixture["document_kind"] == "rendered"
    assert "container" not in v2_fixture["database"]
    assert "budget" not in v2_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v2_fixture, "outputs.schema.json")


# ---------------------------------------------------------------------------
# v1 -> v2
# ---------------------------------------------------------------------------


def test_v1_to_v2_sets_the_rendered_kind(v2: dict[str, Any]) -> None:
    assert v2["schema_version"] == 2
    assert v2["document_kind"] == "rendered"


def test_migration_preserves_the_secrets_namespace(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    """ADR 0012: the runbook's fragment would have dropped this field.

    ``secrets.namespace`` is in ``test_render_isolation.MUST_DIFFER`` and in
    ``evidence.ISOLATED_FIELDS``, so losing it would silently remove a tested
    isolation field.
    """
    assert v2["secrets"]["namespace"] == v1["secrets"]["namespace"]
    assert v2["secrets"]["status"] == "planned"


def test_migration_derives_the_health_route(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    """The health route is a pure function of the domain, so v1 determines it."""
    assert v2["routes"]["health"] == {
        "status": "planned",
        "url": f"https://{v1['project']['domain']}{naming.HEALTH_ROUTE_PATH}",
    }


def test_health_route_constant_agrees_with_naming() -> None:
    """The copy in output_migrations exists only to avoid an import cycle."""
    assert output_migrations.HEALTH_ROUTE_PATH == naming.HEALTH_ROUTE_PATH


def test_migration_does_not_invent_required_names(v2: dict[str, Any]) -> None:
    """A v1 document predates every declaration, so the honest answer is none.

    Copying today's contract in would assert that it applied retroactively.
    """
    assert v2["secrets"]["required_names"] == []


def test_v1_to_v2_preserves_every_other_field(v1: dict[str, Any], v2: dict[str, Any]) -> None:
    for key in ("project", "compose", "database", "jwt", "storage", "backup", "capabilities"):
        assert v2[key] == v1[key], key
    assert v2["template_version"] == v1["template_version"]


def test_migration_does_not_mutate_its_input(v1: dict[str, Any]) -> None:
    before = json.dumps(v1, sort_keys=True)
    output_migrations.migrate_rendered(
        v1,
        secrets_contract_sha256=CONTRACT_DIGEST,
        database_budget=BUDGET,
        database_container=CONTAINER,
        access_profiles=profiles_for(v1),
        documentation_role=documentation_role_for(v1),
        statement_timeouts=statement_timeouts_for(v1),
        api_connection_budget=api_budget_for(v1),
        app_docs_url=app_docs_url_for(v1),
        auth_connection_budget=auth_budget_for(v1),
        storage_connection_budget=storage_budget_for(v1),
        pooler_pool_size=pooler_pool_size_for(v1),
        storage_route_url=storage_route_url_for(v1),
        storage_settings=storage_settings_for(v1),
        backup_bucket=backup_bucket_for(v1),
        backup_retain_full=backup_retain_full_for(v1),
        backup_network=backup_network_for(v1),
    )
    assert json.dumps(v1, sort_keys=True) == before


# ---------------------------------------------------------------------------
# v2 -> v3
# ---------------------------------------------------------------------------


def test_the_committed_v2_fixture_migrates_and_validates(v2_fixture: dict[str, Any]) -> None:
    """The v2 step alone no longer produces a valid document, and should not.

    Migrating v2 -> v3 lands on a version the schema stopped accepting when it
    moved to 4. That is the version bump working: what has to be true is that
    the *chain* reaches something valid, not that any single link does.
    """
    at_three = output_migrations.migrate_v2_to_v3(
        v2_fixture, database_budget=BUDGET, database_container=CONTAINER
    )
    assert at_three["schema_version"] == 3
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_three, "outputs.schema.json")

    at_four = output_migrations.migrate_v3_to_v4(at_three, access_profiles=profiles_for(at_three))
    assert at_four["schema_version"] == 4
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_four, "outputs.schema.json")

    at_five = output_migrations.migrate_v4_to_v5(at_four)
    assert at_five["schema_version"] == 5
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_five, "outputs.schema.json")

    migrated = output_migrations.migrate_v5_to_v6(
        at_five, documentation_role=documentation_role_for(at_five)
    )
    assert migrated["schema_version"] == 6
    migrated = output_migrations.migrate_v6_to_v7(
        migrated, statement_timeouts=statement_timeouts_for(migrated)
    )
    assert migrated["schema_version"] == 7
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )
    assert migrated["schema_version"] == 8
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(migrated, app_docs_url=app_docs_url_for(migrated))
    assert migrated["schema_version"] == 9
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    assert migrated["schema_version"] == 10
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    assert migrated["schema_version"] == 11
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_the_whole_chain_validates(chained: dict[str, Any]) -> None:
    """v1 -> v2 -> v3 -> v4 -> v5 -> v6 -> v7 end to end, not only the newest link (ADR 0027)."""
    assert chained["schema_version"] == output_migrations.CURRENT_VERSION
    assert chained["document_kind"] == "rendered"
    config.validate_against_schema(chained, "outputs.schema.json")


def test_v3_carries_the_supplied_budget_and_container(v3: dict[str, Any]) -> None:
    assert v3["database"]["budget"] == BUDGET
    assert v3["database"]["container"] == CONTAINER


def test_v3_adds_no_observed_block(v3: dict[str, Any]) -> None:
    """The rendered branch has no `observed`, and the migrator does not add one.

    A migrator that emitted `{"status": "not_observed", ...}` here would be
    producing a field that only the deployed branch has, which is how a
    migrated document starts looking like state somebody measured.
    """
    assert "observed" not in v3["database"]


def test_v3_preserves_every_other_database_member(
    v2_fixture: dict[str, Any],
) -> None:
    migrated = output_migrations.migrate_v2_to_v3(
        v2_fixture, database_budget=BUDGET, database_container=CONTAINER
    )
    for key in ("name", "roles", "pooled", "direct"):
        assert migrated["database"][key] == v2_fixture["database"][key], key


def test_v3_leaves_both_endpoints_unavailable(v3: dict[str, Any]) -> None:
    """D41: Session 3 offers no client endpoint, and a migration invents none."""
    for endpoint in ("pooled", "direct"):
        assert v3["database"][endpoint]["status"] == "unavailable"
        assert v3["database"][endpoint]["available_from_session"] == 4
        assert v3["database"][endpoint]["url"] is None


def test_budget_members_agree_with_config() -> None:
    """The copy in output_migrations exists to keep this module dependency-free."""
    assert output_migrations.BUDGET_MEMBERS == frozenset(config.database_budget({}))


def test_current_version_agrees_with_the_renderer() -> None:
    """One number, three places. This is the test that keeps them one number."""
    from agentic_postgres import deployed_output

    assert output_migrations.CURRENT_VERSION == deployed_output.SCHEMA_VERSION
    rendered = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    assert rendered["schema_version"] == output_migrations.CURRENT_VERSION


# ---------------------------------------------------------------------------
# What the v3 step refuses to guess
# ---------------------------------------------------------------------------


def test_migration_requires_a_real_contract_digest(v1: dict[str, Any]) -> None:
    """The `inputs` block's whole value is that its digests are real."""
    with pytest.raises(MigrationError, match="64 lowercase hex"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256="<computed SHA-256>",
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
            documentation_role=documentation_role_for(v1),
            statement_timeouts=statement_timeouts_for(v1),
            api_connection_budget=api_budget_for(v1),
            app_docs_url=app_docs_url_for(v1),
            auth_connection_budget=auth_budget_for(v1),
            storage_connection_budget=storage_budget_for(v1),
            pooler_pool_size=pooler_pool_size_for(v1),
            storage_route_url=storage_route_url_for(v1),
            storage_settings=storage_settings_for(v1),
            backup_bucket=backup_bucket_for(v1),
            backup_retain_full=backup_retain_full_for(v1),
            backup_network=backup_network_for(v1),
        )


def test_migrated_inputs_carry_the_supplied_digest(v5: dict[str, Any]) -> None:
    assert v5["inputs"]["secrets_contract_sha256"] == CONTRACT_DIGEST
    assert len(v5["inputs"]) == 5


@pytest.mark.parametrize(
    "budget",
    [
        pytest.param({}, id="empty"),
        pytest.param({"shared_buffers_mb": 128}, id="partial"),
        pytest.param({**BUDGET, "extra_mb": 1}, id="extra-member"),
    ],
)
def test_an_incomplete_budget_is_refused(v2_fixture: dict[str, Any], budget: dict) -> None:
    with pytest.raises(MigrationError, match="database_budget must have exactly"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=budget, database_container=CONTAINER
        )


@pytest.mark.parametrize("bad", [0, -1, "128", 12.5, True])
def test_a_non_positive_integer_budget_member_is_refused(
    v2_fixture: dict[str, Any], bad: Any
) -> None:
    """`True` is in this list on purpose: it is an int, and it is not a size."""
    with pytest.raises(MigrationError, match="positive integers"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture,
            database_budget={**BUDGET, "shared_buffers_mb": bad},
            database_container=CONTAINER,
        )


@pytest.mark.parametrize("bad", ["", "Apg-Upper", "-leading", "has space", "sl/ash", 5, None])
def test_an_unusable_container_name_is_refused(v2_fixture: dict[str, Any], bad: Any) -> None:
    with pytest.raises(MigrationError, match="not a usable Compose name"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=bad
        )


def test_the_migrator_never_derives_a_container_name() -> None:
    """ADR 0002: one derivation path per name, and it is not this module.

    Asserted on the import graph rather than on behaviour, because the failure
    this prevents is someone adding `from agentic_postgres import naming` and a
    one-line `f"apg-{key}-postgres-1"` that agrees with `naming` until it does
    not.
    """
    source = (REPO_ROOT / "src" / "agentic_postgres" / "output_migrations.py").read_text("utf-8")
    assert "import naming" not in source
    assert "postgres-1" not in source


# ---------------------------------------------------------------------------
# What the migrator refuses
# ---------------------------------------------------------------------------


def test_a_current_version_document_is_not_migrated_again(
    chained: dict[str, Any], v5: dict[str, Any]
) -> None:
    """Replaces the v2 form of this assertion, applied to the current version.

    ADR 0017's rule: a test may only be replaced by a stricter one. This is the
    same property -- migrating a document that is already current is a no-op and
    is refused -- now asserted through the chaining entry point as well as the
    single step, which the previous version did not cover.
    """
    with pytest.raises(MigrationError, match="already version 13"):
        output_migrations.migrate_rendered(
            chained,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(chained),
            documentation_role=documentation_role_for(chained),
            statement_timeouts=statement_timeouts_for(chained),
            api_connection_budget=api_budget_for(chained),
            app_docs_url=app_docs_url_for(chained),
            auth_connection_budget=auth_budget_for(chained),
            storage_connection_budget=storage_budget_for(chained),
            pooler_pool_size=pooler_pool_size_for(chained),
            storage_route_url=storage_route_url_for(chained),
            storage_settings=storage_settings_for(chained),
            backup_bucket=backup_bucket_for(chained),
            backup_retain_full=backup_retain_full_for(chained),
            backup_network=backup_network_for(chained),
        )
    with pytest.raises(MigrationError, match="already version 5"):
        output_migrations.migrate_v4_to_v5(v5)


def test_a_v2_document_is_still_refused_by_the_v1_step(v2_fixture: dict[str, Any]) -> None:
    """The single step keeps its own narrow refusal."""
    with pytest.raises(MigrationError, match="already version 2"):
        output_migrations.migrate_v1_to_v2(v2_fixture, secrets_contract_sha256=CONTRACT_DIGEST)


def test_an_unknown_version_is_refused(v1: dict[str, Any]) -> None:
    v1["schema_version"] = 99
    with pytest.raises(MigrationError, match="only versions 1 through 12"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
            documentation_role=documentation_role_for(v1),
            statement_timeouts=statement_timeouts_for(v1),
            api_connection_budget=api_budget_for(v1),
            app_docs_url=app_docs_url_for(v1),
            auth_connection_budget=auth_budget_for(v1),
            storage_connection_budget=storage_budget_for(v1),
            pooler_pool_size=pooler_pool_size_for(v1),
            storage_route_url=storage_route_url_for(v1),
            storage_settings=storage_settings_for(v1),
            backup_bucket=backup_bucket_for(v1),
            backup_retain_full=backup_retain_full_for(v1),
            backup_network=backup_network_for(v1),
        )


def test_an_incomplete_v1_document_is_refused(v1: dict[str, Any]) -> None:
    del v1["jwt"]
    with pytest.raises(MigrationError, match="missing"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
            documentation_role=documentation_role_for(v1),
            statement_timeouts=statement_timeouts_for(v1),
            api_connection_budget=api_budget_for(v1),
            app_docs_url=app_docs_url_for(v1),
            auth_connection_budget=auth_budget_for(v1),
            storage_connection_budget=storage_budget_for(v1),
            pooler_pool_size=pooler_pool_size_for(v1),
            storage_route_url=storage_route_url_for(v1),
            storage_settings=storage_settings_for(v1),
            backup_bucket=backup_bucket_for(v1),
            backup_retain_full=backup_retain_full_for(v1),
            backup_network=backup_network_for(v1),
        )


def test_an_incomplete_v2_document_is_refused(v2_fixture: dict[str, Any]) -> None:
    del v2_fixture["jwt"]
    with pytest.raises(MigrationError, match="not a complete version 2"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_a_document_with_unexpected_fields_is_refused(v1: dict[str, Any]) -> None:
    """Something claiming to be v1 while carrying v2 fields is not v1."""
    v1["tls"] = {"status": "issued"}
    with pytest.raises(MigrationError, match="no version 1 document has"):
        output_migrations.migrate_rendered(
            v1,
            secrets_contract_sha256=CONTRACT_DIGEST,
            database_budget=BUDGET,
            database_container=CONTAINER,
            access_profiles=profiles_for(v1),
            documentation_role=documentation_role_for(v1),
            statement_timeouts=statement_timeouts_for(v1),
            api_connection_budget=api_budget_for(v1),
            app_docs_url=app_docs_url_for(v1),
            auth_connection_budget=auth_budget_for(v1),
            storage_connection_budget=storage_budget_for(v1),
            pooler_pool_size=pooler_pool_size_for(v1),
            storage_route_url=storage_route_url_for(v1),
            storage_settings=storage_settings_for(v1),
            backup_bucket=backup_bucket_for(v1),
            backup_retain_full=backup_retain_full_for(v1),
            backup_network=backup_network_for(v1),
        )


def test_a_v2_document_carrying_deployed_fields_is_refused(v2_fixture: dict[str, Any]) -> None:
    v2_fixture["observed_at"] = "2026-08-07T00:00:00Z"
    with pytest.raises(MigrationError, match="no version 2 rendered document has"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_a_deployed_document_is_not_migrated(v2_fixture: dict[str, Any]) -> None:
    """A deployed document is an observation of a host, and migrating one would
    republish those observations under a version that never measured them."""
    v2_fixture["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v2_to_v3(
            v2_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


def test_there_is_no_way_to_produce_a_deployed_document() -> None:
    """ADR 0012: every field that makes a document `deployed` is an observation.

    Asserted against the module's public surface rather than by inspecting the
    source, so a future function that emitted one would have to be added to
    ``__all__`` unnoticed to escape this.
    """
    exported = set(output_migrations.__all__)
    assert not any("deploy" in name.lower() for name in exported)
    assert "migrate_rendered" in exported


# ---------------------------------------------------------------------------
# Document-kind rejection at the boundary
# ---------------------------------------------------------------------------


def test_rendered_output_is_reported_as_rendered() -> None:
    document = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    assert output_migrations.document_kind(document) == "rendered"
    output_migrations.require_kind(document, "rendered")


def test_rendered_output_is_refused_where_deployed_state_is_required() -> None:
    """The two files share a basename, so this is the realistic mistake."""
    document = json.loads(
        (REPO_ROOT / ".generated" / "fixture-alpha-dev" / "outputs.json").read_text("utf-8")
    )
    with pytest.raises(MigrationError, match="expected a 'deployed'"):
        output_migrations.require_kind(document, "deployed")


def test_a_v1_document_is_reported_as_rendered(v1: dict[str, Any]) -> None:
    """v1 predates the discriminator, and everything it could be was rendered."""
    assert output_migrations.document_kind(v1) == "rendered"


def test_an_unknown_document_kind_is_refused() -> None:
    with pytest.raises(MigrationError, match="document_kind is missing or unknown"):
        output_migrations.document_kind({"schema_version": 2, "document_kind": "observed"})


def test_a_missing_schema_version_is_refused() -> None:
    with pytest.raises(MigrationError, match="schema_version"):
        output_migrations.detect_version({"document_kind": "rendered"})


# ---------------------------------------------------------------------------
# v3 -> v4 (ADR 0041)
# ---------------------------------------------------------------------------


def test_v3_fixture_is_version_three_and_no_longer_validates(v3_fixture: dict[str, Any]) -> None:
    """The committed Session 3 render, and the claim that makes v4 a real bump.

    This is the version every deployed host is running right now, so a v3
    document that still validated would mean the bump had changed a label and
    nothing else.
    """
    assert output_migrations.detect_version(v3_fixture) == 3
    assert v3_fixture["document_kind"] == "rendered"
    assert "access_profiles" not in v3_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v3_fixture, "outputs.schema.json")


def test_the_committed_v3_fixture_migrates_and_validates(v3_fixture: dict[str, Any]) -> None:
    at_four = output_migrations.migrate_v3_to_v4(
        v3_fixture, access_profiles=profiles_for(v3_fixture)
    )
    assert at_four["schema_version"] == 4
    at_five = output_migrations.migrate_v4_to_v5(at_four)
    assert at_five["schema_version"] == 5
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_five, "outputs.schema.json")

    migrated = output_migrations.migrate_v5_to_v6(
        at_five, documentation_role=documentation_role_for(at_five)
    )
    assert migrated["schema_version"] == 6
    migrated = output_migrations.migrate_v6_to_v7(
        migrated, statement_timeouts=statement_timeouts_for(migrated)
    )
    assert migrated["schema_version"] == 7
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )
    assert migrated["schema_version"] == 8
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(migrated, app_docs_url=app_docs_url_for(migrated))
    assert migrated["schema_version"] == 9
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    assert migrated["schema_version"] == 10
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    assert migrated["schema_version"] == 11
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v4_carries_three_profiles_over_two_transports(v4: dict[str, Any]) -> None:
    profiles = v4["database"]["access_profiles"]
    assert set(profiles) == {"runtime_pooled", "runtime_direct", "migration_direct"}
    assert {profile["transport"] for profile in profiles.values()} == {"pooled", "direct"}
    assert profiles["runtime_pooled"]["role"] == profiles["runtime_direct"]["role"]
    assert profiles["migration_direct"]["role"] != profiles["runtime_direct"]["role"]


def test_v4_leaves_every_profile_unprovisioned(v4: dict[str, Any]) -> None:
    """A migration of an archived document cannot produce a deployment."""
    for name, profile in v4["database"]["access_profiles"].items():
        assert profile["status"] == "unavailable", name
        assert profile["password_secret_ref"] is None, name
        assert profile["available_from_session"] == 4, name


def test_v4_preserves_every_other_database_member(v3_fixture: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v3_to_v4(
        v3_fixture, access_profiles=profiles_for(v3_fixture)
    )
    for key in ("name", "container", "roles", "budget", "pooled", "direct"):
        assert migrated["database"][key] == v3_fixture["database"][key], key


def test_v4_adds_no_observed_block(v4: dict[str, Any]) -> None:
    assert "observed" not in v4["database"]


def test_profile_transports_agree_with_the_schema() -> None:
    """The migrator's copy of the pairing, checked against the authority.

    The schema fixes each profile's transport with a `const`; this module keeps
    its own mapping so that it depends on nothing. Two copies of a fact need a
    test between them, or they are two facts.
    """
    schema = config.load_schema("outputs.schema.json")
    profiles = schema["$defs"]["accessProfiles"]["properties"]
    from_schema = {
        name: definition["allOf"][1]["properties"]["transport"]["const"]
        for name, definition in profiles.items()
    }
    assert from_schema == output_migrations.ACCESS_PROFILE_TRANSPORTS


def test_a_profile_naming_the_wrong_transport_is_refused(v3_fixture: dict[str, Any]) -> None:
    profiles = profiles_for(v3_fixture)
    profiles["runtime_pooled"]["transport"] = "direct"
    with pytest.raises(MigrationError, match="that profile is the 'pooled' transport"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_profile_naming_an_undeclared_role_is_refused(v3_fixture: dict[str, Any]) -> None:
    """The reason this module validates rather than derives.

    A caller that invents a role name gets a refusal naming the document's own
    declaration, not a document that quietly carries a role nothing created.
    """
    profiles = profiles_for(v3_fixture)
    profiles["migration_direct"]["role"] = "apg_some_other_project_migration_user"
    with pytest.raises(MigrationError, match=r"does not declare in database.roles"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("status", "available", id="status"),
        pytest.param("password_secret_ref", "app_runtime_password", id="secret-ref"),
    ],
)
def test_a_provisioned_profile_is_refused(
    v3_fixture: dict[str, Any], field: str, value: str
) -> None:
    """Either half alone is enough to refuse, which is why both are parametrized.

    A v3 document records no bound port and no credential. A migrator that
    accepted `available` would be publishing a deployment nobody performed, and
    one that accepted a secret reference would be naming a secret that may never
    have been declared.
    """
    profiles = profiles_for(v3_fixture)
    profiles["runtime_direct"][field] = value
    with pytest.raises(MigrationError, match="claims to be provisioned"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


@pytest.mark.parametrize(
    "profiles",
    [
        pytest.param({}, id="empty"),
        pytest.param({"runtime_pooled": {}}, id="partial"),
        pytest.param(
            {
                "runtime_pooled": {},
                "runtime_direct": {},
                "migration_direct": {},
                "runtime_extra": {},
            },
            id="extra-profile",
        ),
    ],
)
def test_an_incomplete_profile_set_is_refused(v3_fixture: dict[str, Any], profiles: dict) -> None:
    with pytest.raises(MigrationError, match="access_profiles must have exactly"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_profile_missing_a_member_is_refused(v3_fixture: dict[str, Any]) -> None:
    profiles = profiles_for(v3_fixture)
    del profiles["runtime_direct"]["role"]
    with pytest.raises(MigrationError, match="must have exactly"):
        output_migrations.migrate_v3_to_v4(v3_fixture, access_profiles=profiles)


def test_a_v3_document_is_still_refused_by_the_v2_step(v3_fixture: dict[str, Any]) -> None:
    """Each single step keeps its own narrow refusal as the chain grows."""
    with pytest.raises(MigrationError, match="already version 3"):
        output_migrations.migrate_v2_to_v3(
            v3_fixture, database_budget=BUDGET, database_container=CONTAINER
        )


# ---------------------------------------------------------------------------
# v4 -> v5 (ADR 0053)
# ---------------------------------------------------------------------------


def test_v4_fixture_is_version_four_and_no_longer_validates(v4_fixture: dict[str, Any]) -> None:
    """The committed Session 4 render -- the version every host is running now.

    A v4 document that still validated would mean version 5 had changed a label
    and nothing else, which is a real risk here precisely because the rendered
    branch gained no field. The bump is real because the *schema* moved: the
    rendered branch's `schema_version` enum accepts one value, and it is 5.
    """
    assert output_migrations.detect_version(v4_fixture) == 4
    assert v4_fixture["document_kind"] == "rendered"
    assert "access_profiles" in v4_fixture["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v4_fixture, "outputs.schema.json")


def test_the_committed_v4_fixture_migrates_and_validates(v4_fixture: dict[str, Any]) -> None:
    at_five = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert at_five["schema_version"] == 5
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(at_five, "outputs.schema.json")

    migrated = output_migrations.migrate_v5_to_v6(
        at_five, documentation_role=documentation_role_for(at_five)
    )
    assert migrated["schema_version"] == 6
    migrated = output_migrations.migrate_v6_to_v7(
        migrated, statement_timeouts=statement_timeouts_for(migrated)
    )
    assert migrated["schema_version"] == 7
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )
    assert migrated["schema_version"] == 8
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(migrated, app_docs_url=app_docs_url_for(migrated))
    assert migrated["schema_version"] == 9
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    assert migrated["schema_version"] == 10
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    assert migrated["schema_version"] == 11
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v5_changes_exactly_one_field(v4_fixture: dict[str, Any]) -> None:
    """The whole content of the step, asserted as a difference rather than described.

    Version 5's additions are all on the deployed branch, so a rendered document
    gains nothing. If a later change makes this step add a member, this fails --
    which is the point: a rendered document that grew a status or a checksum
    would be carrying an observation, and that is the boundary ADR 0012 draws.
    """
    migrated = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert migrated == {**v4_fixture, "schema_version": 5}


def test_v5_adds_no_deployed_member(v4_fixture: dict[str, Any]) -> None:
    """Named individually, because each one is a thing a migrator could invent."""
    migrated = output_migrations.migrate_v4_to_v5(v4_fixture)
    assert "api" not in migrated
    assert "observed" not in migrated["database"]
    assert isinstance(migrated["routes"]["rest"], str)
    assert isinstance(migrated["routes"]["docs"], str)
    assert set(migrated["jwt"]) == {"issuer", "audience"}


def test_the_v5_step_still_refuses_a_deployed_document(v4_fixture: dict[str, Any]) -> None:
    """The cheap step is not a way past the checks the expensive ones make."""
    v4_fixture["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_the_v5_step_refuses_an_incomplete_document(v4_fixture: dict[str, Any]) -> None:
    del v4_fixture["jwt"]
    with pytest.raises(MigrationError, match="not a complete version 4"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_the_v5_step_refuses_a_document_carrying_deployed_fields(
    v4_fixture: dict[str, Any],
) -> None:
    v4_fixture["observed_at"] = "2026-08-11T00:00:00Z"
    with pytest.raises(MigrationError, match="no version 4 rendered document has"):
        output_migrations.migrate_v4_to_v5(v4_fixture)


def test_a_v3_document_is_refused_by_the_v5_step(v3_fixture: dict[str, Any]) -> None:
    """A v3 document has every top-level key a v4 one has, and is not one.

    This is why the step looks inside `database` as well as at the top level:
    version 4's addition was a member, so the outer shape alone cannot tell the
    two apart, and a step that skipped v3 -> v4 would silently produce a v5
    document with no `access_profiles` in it.
    """
    with pytest.raises(MigrationError, match="only version 4 can be migrated to 5"):
        output_migrations.migrate_v4_to_v5(v3_fixture)

    mislabelled = {**v3_fixture, "schema_version": 4}
    with pytest.raises(MigrationError, match="access_profiles is missing"):
        output_migrations.migrate_v4_to_v5(mislabelled)


def test_the_v5_step_does_not_mutate_its_input(v4_fixture: dict[str, Any]) -> None:
    before = json.dumps(v4_fixture, sort_keys=True)
    output_migrations.migrate_v4_to_v5(v4_fixture)
    assert json.dumps(v4_fixture, sort_keys=True) == before


def test_a_v4_document_is_still_refused_by_the_v3_step(v4_fixture: dict[str, Any]) -> None:
    """Each single step keeps its own narrow refusal as the chain grows."""
    with pytest.raises(MigrationError, match="already version 4"):
        output_migrations.migrate_v3_to_v4(v4_fixture, access_profiles=profiles_for(v4_fixture))


# ---------------------------------------------------------------------------
# v5 -> v6 (D158): the documentation role
# ---------------------------------------------------------------------------


def test_v5_fixture_is_version_five_and_no_longer_validates(v5_fixture: dict[str, Any]) -> None:
    """The committed Session 5 render, and the claim that makes v6 a real bump.

    A v5 document that still validated would mean the bump had changed a label
    and nothing else. It does not: databaseRoles is required with
    additionalProperties: false, so a document without the fourteenth role
    is refused by the current schema.
    """
    assert output_migrations.detect_version(v5_fixture) == 5
    assert v5_fixture["document_kind"] == "rendered"
    assert "api_documentation" not in v5_fixture["database"]["roles"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v5_fixture, "outputs.schema.json")


def test_the_committed_v5_fixture_migrates_and_validates(v5_fixture: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v5_to_v6(
        v5_fixture, documentation_role=documentation_role_for(v5_fixture)
    )
    assert migrated["schema_version"] == 6
    migrated = output_migrations.migrate_v6_to_v7(
        migrated, statement_timeouts=statement_timeouts_for(migrated)
    )
    assert migrated["schema_version"] == 7
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )
    assert migrated["schema_version"] == 8
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(migrated, app_docs_url=app_docs_url_for(migrated))
    assert migrated["schema_version"] == 9
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    assert migrated["schema_version"] == 10
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    assert migrated["schema_version"] == 11
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v6_changes_exactly_one_field(v5_fixture: dict[str, Any]) -> None:
    """The whole content of the step, asserted as a difference rather than described.

    Goes red if the step ever adds a second member -- which for a *rendered*
    document would mean it had grown an observation, the boundary ADR 0012 draws.
    """
    role = documentation_role_for(v5_fixture)
    migrated = output_migrations.migrate_v5_to_v6(v5_fixture, documentation_role=role)

    assert migrated["database"]["roles"]["api_documentation"] == role
    before = {k: v for k, v in v5_fixture.items() if k != "schema_version"}
    after = {k: v for k, v in migrated.items() if k != "schema_version"}
    after["database"] = dict(after["database"])
    after["database"]["roles"] = {
        k: v for k, v in after["database"]["roles"].items() if k != "api_documentation"
    }
    assert after == before


def test_the_v6_step_does_not_mutate_its_input(v5_fixture: dict[str, Any]) -> None:
    """An in-place migrator would leave the caller holding a document that is
    neither the version it read nor the version it asked for."""
    snapshot = json.loads(json.dumps(v5_fixture))
    output_migrations.migrate_v5_to_v6(
        v5_fixture, documentation_role=documentation_role_for(v5_fixture)
    )
    assert v5_fixture == snapshot


def test_the_v6_step_refuses_a_deployed_document(v5_fixture: dict[str, Any]) -> None:
    v5_fixture["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v5_to_v6(v5_fixture, documentation_role="apg_x_api_documentation")


def test_the_v6_step_refuses_a_role_that_is_not_an_identifier(
    v5_fixture: dict[str, Any],
) -> None:
    with pytest.raises(MigrationError, match="not a bare lowercase SQL identifier"):
        output_migrations.migrate_v5_to_v6(v5_fixture, documentation_role="Apg-Docs Role")


def test_the_v6_step_refuses_a_role_the_document_already_uses(
    v5_fixture: dict[str, Any],
) -> None:
    """The refusal this step adds on top of the v3 pattern.

    Two role keys naming one role is a document in which a grant written for the
    documentation role reaches `app_runtime` instead -- and every check that
    reads role names by key would agree with itself while doing it.
    """
    with pytest.raises(MigrationError, match="already this document's"):
        output_migrations.migrate_v5_to_v6(
            v5_fixture, documentation_role=v5_fixture["database"]["roles"]["app_runtime"]
        )


def test_the_v6_step_refuses_a_document_that_already_has_the_role(
    v5_fixture: dict[str, Any],
) -> None:
    role = documentation_role_for(v5_fixture)
    once = output_migrations.migrate_v5_to_v6(v5_fixture, documentation_role=role)
    once["schema_version"] = 5
    with pytest.raises(MigrationError, match="already names api_documentation"):
        output_migrations.migrate_v5_to_v6(once, documentation_role=role)


def test_the_role_pattern_agrees_with_the_schema() -> None:
    """This module keeps its own copy because it depends on nothing.

    Two copies of a fact with a test between them are one fact. Goes red if
    either the schema's ``postgresIdentifier`` or the migrator's copy moves
    without the other.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    assert (
        schema["$defs"]["postgresIdentifier"]["pattern"]
        == output_migrations._POSTGRES_IDENTIFIER.pattern
    )


# ---------------------------------------------------------------------------
# v6 -> v7 (D197, ADR 0067): the statement timeouts
# ---------------------------------------------------------------------------


def timeouts_for(document: dict[str, Any]) -> dict[str, str]:
    """A valid argument for the v7 step, read from the document under test."""
    roles = document["database"]["roles"]
    return {roles["app_runtime"]: "30s", roles["anon"]: "2s", roles["authenticated"]: "5s"}


def test_a_v6_document_no_longer_validates(v6_document: dict[str, Any]) -> None:
    """The claim that makes 7 a real bump rather than a relabelling.

    `statement_timeouts` is required on both branches with
    additionalProperties: false, so a document without it is refused by the
    current schema. If this ever passes, the version moved and the contract
    did not.
    """
    assert output_migrations.detect_version(v6_document) == 6
    assert "statement_timeouts" not in v6_document["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v6_document, "outputs.schema.json")


def test_the_v7_step_produces_a_document_that_validates(v6_document: dict[str, Any]) -> None:
    migrated = output_migrations.migrate_v6_to_v7(
        v6_document, statement_timeouts=timeouts_for(v6_document)
    )
    assert migrated["schema_version"] == 7
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )
    assert migrated["schema_version"] == 8
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(migrated, app_docs_url=app_docs_url_for(migrated))
    assert migrated["schema_version"] == 9
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    assert migrated["schema_version"] == 10
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(migrated, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    assert migrated["schema_version"] == 11
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v7_changes_exactly_one_field(v6_document: dict[str, Any]) -> None:
    """The whole content of the step, asserted as a difference rather than described."""
    timeouts = timeouts_for(v6_document)
    migrated = output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)

    assert migrated["database"]["statement_timeouts"] == timeouts
    before = {k: v for k, v in v6_document.items() if k != "schema_version"}
    after = {k: v for k, v in migrated.items() if k != "schema_version"}
    after["database"] = {k: v for k, v in after["database"].items() if k != "statement_timeouts"}
    assert after == before


def test_the_timeouts_are_written_sorted(v6_document: dict[str, Any]) -> None:
    """The bootstrap plane issues these in the document's order.

    An unsorted map means two renders of one project can produce two statement
    lists that differ only in order -- which is a diff an operator has to read
    and dismiss, every time.
    """
    roles = v6_document["database"]["roles"]
    unsorted = {roles["authenticated"]: "5s", roles["anon"]: "2s", roles["app_runtime"]: "30s"}
    migrated = output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=unsorted)
    written = list(migrated["database"]["statement_timeouts"])
    assert written == sorted(written)


def test_the_v7_step_does_not_mutate_its_input(v6_document: dict[str, Any]) -> None:
    snapshot = json.loads(json.dumps(v6_document))
    output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts_for(v6_document))
    assert v6_document == snapshot


def test_the_v7_step_refuses_a_deployed_document(v6_document: dict[str, Any]) -> None:
    timeouts = timeouts_for(v6_document)
    v6_document["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)


def test_the_v7_step_refuses_a_timeout_on_a_role_the_document_does_not_name(
    v6_document: dict[str, Any],
) -> None:
    """The refusal this step exists for, and the shape of the defect it answers.

    A timeout written for a role nothing created is applied to nothing and
    reports nothing -- which is exactly how the manifest's timeouts spent five
    runs validated and unapplied (D197). Accepting one here would put that
    silence back, one layer down.
    """
    timeouts = timeouts_for(v6_document)
    timeouts["apg_some_other_project_anon"] = "2s"
    with pytest.raises(MigrationError, match=r"which this document's database\.roles"):
        output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)


@pytest.mark.parametrize(
    "duration",
    [
        "0",  # PostgreSQL reads this as *disabled*
        "0s",
        "0ms",
        "30",  # a bare integer is milliseconds, not seconds
        "30 s",
        "30S",
        "1m",
        "1min",
        "1h",
        "030s",
        "100000s",  # six digits, one past the grammar
        "",
        "5s;",
        "5s DROP",
    ],
)
def test_the_v7_step_refuses_a_duration_outside_the_grammar(
    v6_document: dict[str, Any], duration: str
) -> None:
    """Written as literals rather than derived from the pattern.

    A parametrization computed from the constant under test collapses to an
    empty parameter set the moment the constant is emptied, and pytest reports
    an empty set as a pass (D190). These fourteen strings do not move when the
    pattern does.
    """
    roles = v6_document["database"]["roles"]
    with pytest.raises(MigrationError, match="not a strict"):
        output_migrations.migrate_v6_to_v7(
            v6_document, statement_timeouts={roles["anon"]: duration}
        )


@pytest.mark.parametrize("duration", ["100ms", "1s", "2s", "5s", "30s", "99999s", "1ms"])
def test_the_v7_step_accepts_the_grammar_the_schema_admits(
    v6_document: dict[str, Any], duration: str
) -> None:
    """The control for the refusals above.

    Without it, a pattern that rejected everything would pass fourteen tests
    and look thorough.
    """
    roles = v6_document["database"]["roles"]
    migrated = output_migrations.migrate_v6_to_v7(
        v6_document, statement_timeouts={roles["anon"]: duration}
    )
    assert migrated["database"]["statement_timeouts"][roles["anon"]] == duration


def test_the_v7_step_refuses_a_document_that_already_carries_the_field(
    v6_document: dict[str, Any],
) -> None:
    timeouts = timeouts_for(v6_document)
    once = output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)
    once["schema_version"] = 6
    with pytest.raises(MigrationError, match="already carries statement_timeouts"):
        output_migrations.migrate_v6_to_v7(once, statement_timeouts=timeouts)


def test_the_v7_step_refuses_a_document_that_is_already_version_seven(
    v6_document: dict[str, Any],
) -> None:
    timeouts = timeouts_for(v6_document)
    once = output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)
    with pytest.raises(MigrationError, match="already version 7"):
        output_migrations.migrate_v6_to_v7(once, statement_timeouts=timeouts)


def test_a_v5_document_is_refused_by_the_v7_step(v5_fixture: dict[str, Any]) -> None:
    """The cheap step is not a way past the expensive one's checks."""
    roles = v5_fixture["database"]["roles"]
    with pytest.raises(MigrationError, match="only version 6 can be migrated to 7"):
        output_migrations.migrate_v6_to_v7(
            v5_fixture, statement_timeouts={roles["app_runtime"]: "30s"}
        )


def test_a_v6_document_missing_its_roles_is_refused(v6_document: dict[str, Any]) -> None:
    timeouts = timeouts_for(v6_document)
    del v6_document["database"]["roles"]["app_runtime"]
    with pytest.raises(MigrationError, match="not a v6 document"):
        output_migrations.migrate_v6_to_v7(v6_document, statement_timeouts=timeouts)


def test_the_duration_pattern_agrees_with_the_schema() -> None:
    """The test the module's own comment claimed and did not have.

    ``output_migrations`` keeps its own copy of the duration grammar because it
    depends on nothing, and the comment beside that copy said a test asserted
    the two agree. None did, for a day. Two copies of a fact with no test
    between them are two facts.
    """
    schema = json.loads((REPO_ROOT / "schemas" / "outputs.schema.json").read_text(encoding="utf-8"))
    published = schema["$defs"]["statementTimeouts"]["patternProperties"]
    assert list(published) == [output_migrations._POSTGRES_IDENTIFIER.pattern], (
        "the schema keys statementTimeouts by something other than a role identifier"
    )
    assert (
        published[output_migrations._POSTGRES_IDENTIFIER.pattern]["pattern"]
        == output_migrations._STATEMENT_TIMEOUT.pattern
    )


# ---------------------------------------------------------------------------
# v7 -> v8 (D161, ADR 0070): the API's connection commitment
# ---------------------------------------------------------------------------


@pytest.fixture
def v7_document(v6_document: dict[str, Any]) -> dict[str, Any]:
    """The committed Session 5 render advanced to 7 -- the v8 step's input."""
    return output_migrations.migrate_v6_to_v7(
        v6_document, statement_timeouts=timeouts_for(v6_document)
    )


def test_a_v7_document_no_longer_validates(v7_document: dict[str, Any]) -> None:
    """`api_connection_budget` is required on both branches, so 8 is a real bump."""
    assert output_migrations.detect_version(v7_document) == 7
    assert "api_connection_budget" not in v7_document["database"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v7_document, "outputs.schema.json")


def test_v8_changes_exactly_one_field(v7_document: dict[str, Any]) -> None:
    budget = api_budget_for(v7_document)
    migrated = output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=budget)

    assert migrated["database"]["api_connection_budget"] == budget
    before = {k: v for k, v in v7_document.items() if k != "schema_version"}
    after = {k: v for k, v in migrated.items() if k != "schema_version"}
    after["database"] = {k: v for k, v in after["database"].items() if k != "api_connection_budget"}
    assert after == before


def test_the_v8_step_does_not_mutate_its_input(v7_document: dict[str, Any]) -> None:
    snapshot = json.loads(json.dumps(v7_document))
    output_migrations.migrate_v7_to_v8(
        v7_document, api_connection_budget=api_budget_for(v7_document)
    )
    assert v7_document == snapshot


def test_the_v8_step_refuses_a_deployed_document(v7_document: dict[str, Any]) -> None:
    v7_document["document_kind"] = "deployed"
    with pytest.raises(MigrationError, match="expected a 'rendered'"):
        output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=13)


@pytest.mark.parametrize("budget", [0, -1, -13])
def test_a_commitment_of_nothing_is_refused(v7_document: dict[str, Any], budget: int) -> None:
    """0 is how PostgreSQL spells 'reject every login', not 'unlimited'."""
    with pytest.raises(MigrationError, match=r"cannot serve a request|must be an integer"):
        output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=budget)


@pytest.mark.parametrize("budget", ["13", 13.0, None, True])
def test_a_commitment_that_is_not_an_integer_is_refused(
    v7_document: dict[str, Any], budget: Any
) -> None:
    """`True` is in this list deliberately: it is an `int` in Python and a
    nonsense connection limit everywhere else."""
    with pytest.raises(MigrationError, match="must be an integer"):
        output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=budget)


def test_a_commitment_that_leaves_nothing_for_anyone_else_is_refused(
    v7_document: dict[str, Any],
) -> None:
    """The document already carries `max_connections`, so a commitment that was
    never going to fit can be refused here rather than on a host."""
    maximum = v7_document["database"]["budget"]["max_connections"]
    with pytest.raises(MigrationError, match="leaves nothing"):
        output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=maximum)


def test_the_v8_step_refuses_a_document_that_already_carries_the_field(
    v7_document: dict[str, Any],
) -> None:
    once = output_migrations.migrate_v7_to_v8(v7_document, api_connection_budget=13)
    once["schema_version"] = 7
    with pytest.raises(MigrationError, match="already carries api_connection_budget"):
        output_migrations.migrate_v7_to_v8(once, api_connection_budget=13)


def test_a_v6_document_is_refused_by_the_v8_step(v6_document: dict[str, Any]) -> None:
    with pytest.raises(MigrationError, match="only version 7 can be migrated to 8"):
        output_migrations.migrate_v7_to_v8(v6_document, api_connection_budget=13)


# ---------------------------------------------------------------------------
# The v8 fixture, and the comparison it makes possible (D245)
# ---------------------------------------------------------------------------

#: A real Session 6 render at version 8, captured with `deploy.sh --render-only`
#: at commit `dfdbddc` -- the last commit that still rendered version 8.
#:
#: **v6, v7 and v8 had no fixture.** Every assertion about `migrate_v6_to_v7` and
#: `migrate_v7_to_v8` was made against a document the earlier steps produced,
#: which is the condition this module's own docstring names: "a document derived
#: from the migrator is a document that agrees with the migrator by
#: construction". The discipline lapsed after v5 and nothing noticed, because a
#: chained document validates against the schema exactly as a rendered one does.
FIXTURE_V8 = REPO_ROOT / "tests" / "fixtures" / "outputs-v8.json"


#: Objects whose **keys are data**, not schema. `statement_timeouts` is keyed by
#: derived role name and holds whatever a manifest declared, so its members
#: differ between any two projects; comparing them compares manifests.
#:
#: Named explicitly rather than inferred. The first draft of the comparison below
#: did not exclude it and reported two "missing" keys that were two roles this
#: fixture's manifest happens to bound -- a rig measuring one level away from its
#: claim, which is the failure this whole module is about.
DATA_KEYED_OBJECTS = ("database.statement_timeouts",)


def document_shape(node: Any, path: str = "") -> set[str]:
    """Every key path in a document, ignoring values.

    Shape rather than equality, because the fixtures describe different projects
    and always will. A key the migrated document lacks is a field the migrator
    never adds; a key only it has is a field the migrator invents. Both are
    silent today: the schema admits either.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            found.add(here)
            if here in DATA_KEYED_OBJECTS:
                continue
            found |= document_shape(value, here)
    elif isinstance(node, list):
        for item in node:
            found |= document_shape(item, f"{path}[]")
    return found


@pytest.fixture
def v8_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_V8.read_text(encoding="utf-8"))


def test_the_v8_fixture_is_a_real_render_at_version_8(v8_fixture: dict[str, Any]) -> None:
    """A genuine version 8 render, and now a superseded one.

    It validated against the schema on the day it was captured and does not
    today, which is the version bump working rather than a defect -- the same
    thing every fixture above says about itself. What is asserted instead is
    what makes it a fixture: the version it claims, the kind it is, and that it
    reaches the current version through the chain.
    """
    assert v8_fixture["schema_version"] == 8
    assert v8_fixture["document_kind"] == "rendered"
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v8_fixture, "outputs.schema.json")

    migrated = output_migrations.migrate_v8_to_v9(
        v8_fixture, app_docs_url=app_docs_url_for(v8_fixture)
    )
    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_the_migrated_v8_has_the_same_shape_as_a_rendered_one(
    v5_fixture: dict[str, Any], v8_fixture: dict[str, Any]
) -> None:
    """The check the missing fixtures made impossible.

    Both documents validate against the same schema, so this is not about
    validity -- a field the renderer writes and the migrator omits is admitted by
    the schema in both directions, and would surface only on a host running a
    migrated document that some later code reads a missing key from.

    Not asserted: field values. The two fixtures describe different projects, and
    a comparison that required otherwise would be a comparison nobody could keep.
    """
    migrated = output_migrations.migrate_v5_to_v6(
        v5_fixture, documentation_role=documentation_role_for(v5_fixture)
    )
    migrated = output_migrations.migrate_v6_to_v7(
        migrated, statement_timeouts=statement_timeouts_for(migrated)
    )
    migrated = output_migrations.migrate_v7_to_v8(
        migrated, api_connection_budget=api_budget_for(migrated)
    )

    rendered_shape = document_shape(v8_fixture)
    migrated_shape = document_shape(migrated)

    never_added = rendered_shape - migrated_shape
    assert not never_added, (
        f"the renderer writes keys the migration chain never adds: {sorted(never_added)}. "
        "A document migrated onto a host would be missing them, and the schema admits that"
    )

    invented = migrated_shape - rendered_shape
    assert not invented, (
        f"the migration chain produces keys no render writes: {sorted(invented)}. "
        "A migrator that invents a field is a second authority on that field"
    )


# ---------------------------------------------------------------------------
# The version 9 step
# ---------------------------------------------------------------------------


@pytest.fixture
def v8_document(v8_fixture: dict[str, Any]) -> dict[str, Any]:
    """A real v8 render -- the v9 step's input, from the fixture rather than the chain."""
    return v8_fixture


def test_v9_adds_the_application_documentation_url(v8_document: dict[str, Any]) -> None:
    url = app_docs_url_for(v8_document)
    migrated = output_migrations.migrate_v8_to_v9(v8_document, app_docs_url=url)

    assert migrated["schema_version"] == 9
    assert migrated["routes"]["app_docs"] == url
    # The page under the documentation root, not the root (ADR 0061).
    assert migrated["routes"]["app_docs"].endswith(naming.DOCS_APP_PAGE_PATH)


def test_v9_does_not_touch_routes_app(v8_document: dict[str, Any]) -> None:
    """The rendered branch has carried `app` since Session 1, measured not assumed.

    A step that added it would be refusing every document it was given, and a
    step that overwrote it would be a second derivation of a URL `naming.derive`
    already owns -- which is what `jwt_issuer` is built from.
    """
    before = v8_document["routes"]["app"]
    migrated = output_migrations.migrate_v8_to_v9(
        v8_document, app_docs_url=app_docs_url_for(v8_document)
    )
    assert migrated["routes"]["app"] == before


def test_v9_refuses_a_document_that_already_carries_app_docs(
    v8_document: dict[str, Any],
) -> None:
    once = output_migrations.migrate_v8_to_v9(
        v8_document, app_docs_url=app_docs_url_for(v8_document)
    )
    once["schema_version"] = 8
    with pytest.raises(MigrationError, match="already carries app_docs"):
        output_migrations.migrate_v8_to_v9(once, app_docs_url=app_docs_url_for(once))


def test_v9_refuses_a_document_with_no_app_route(v8_document: dict[str, Any]) -> None:
    """Not a hypothetical: it is how a hand-built fixture would arrive."""
    broken = {
        **v8_document,
        "routes": {k: v for k, v in v8_document["routes"].items() if k != "app"},
    }
    with pytest.raises(MigrationError, match="carries no app"):
        output_migrations.migrate_v8_to_v9(broken, app_docs_url=app_docs_url_for(broken))


def test_v9_refuses_a_url_that_is_not_https(v8_document: dict[str, Any]) -> None:
    for url in ("http://example.test/docs/app", "/docs/app", "", None, 7):
        with pytest.raises(MigrationError, match="must be an https URL"):
            output_migrations.migrate_v8_to_v9(v8_document, app_docs_url=url)


def test_v9_refuses_a_url_another_route_already_claims(v8_document: dict[str, Any]) -> None:
    """Two routes at one address is a router answering for whichever attached last."""
    for existing in ("docs", "app"):
        with pytest.raises(MigrationError, match="URL of another route"):
            output_migrations.migrate_v8_to_v9(
                v8_document, app_docs_url=v8_document["routes"][existing]
            )


def test_v9_refuses_a_deployed_document(v8_document: dict[str, Any]) -> None:
    """The refusal every step in this module repeats, for the seventh time."""
    deployed = {**v8_document, "document_kind": "deployed"}
    with pytest.raises(MigrationError):
        output_migrations.migrate_v8_to_v9(deployed, app_docs_url=app_docs_url_for(deployed))


def test_v9_does_not_mutate_its_input(v8_document: dict[str, Any]) -> None:
    before = json.dumps(v8_document, sort_keys=True)
    output_migrations.migrate_v8_to_v9(v8_document, app_docs_url=app_docs_url_for(v8_document))
    assert json.dumps(v8_document, sort_keys=True) == before


def test_the_renderer_and_the_migrator_agree_on_the_documentation_url(
    v8_document: dict[str, Any],
) -> None:
    """One authority for the path (ADR 0061), read from both sides.

    `naming.DOCS_APP_PAGE_PATH` is where the renderer gets it. The migrator is
    handed it. If the two ever disagreed, a project migrated onto a host would
    publish a documentation page at an address nothing routes -- and both halves
    would look right in isolation, which is D177 exactly.
    """
    domain = v8_document["project"]["domain"]
    identity = naming.derive(
        slug=v8_document["project"]["slug"],
        environment=v8_document["project"]["environment"],
        domain=domain,
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    assert identity.route_app_docs == app_docs_url_for(v8_document)
    assert identity.route_app_docs_path == naming.DOCS_APP_PAGE_PATH


def test_a_version_9_document_without_the_documentation_route_is_refused(
    v8_document: dict[str, Any],
) -> None:
    """`app_docs` is required, and nothing else was asserting that.

    Found by mutation: removing `app_docs` from the schema's `required` list left
    every test green, because the document the refusal tests use is a **version 8**
    one and the version enum refuses it on its own. So the required-ness was
    riding on a check that would have refused the document anyway -- a guard
    proved by a test that does not need it, which is this repository's own
    defect in miniature.
    """
    migrated = output_migrations.migrate_v8_to_v9(
        v8_document, app_docs_url=app_docs_url_for(v8_document)
    )
    migrated = output_migrations.migrate_v9_to_v10(
        migrated, auth_connection_budget=auth_budget_for(migrated)
    )
    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")

    without = {
        **migrated,
        "routes": {k: v for k, v in migrated["routes"].items() if k != "app_docs"},
    }
    # No message match: the schema is a top-level oneOf, so jsonschema reports
    # "not valid under any of the given schemas" and names no field. The control
    # is the pair -- the same document WITH the route validates two lines above,
    # so the refusal is about the one key that was removed.
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(without, "outputs.schema.json")


# ---------------------------------------------------------------------------
# The version 10 step
# ---------------------------------------------------------------------------

#: A real Session 6 render at version 9, captured with `deploy.sh --render-only`
#: at commit `3e4a155` -- the last commit that still rendered version 9. Taken
#: before the bump, because afterwards one cannot be produced from this tree
#: (D245).
FIXTURE_V9 = REPO_ROOT / "tests" / "fixtures" / "outputs-v9.json"


@pytest.fixture
def v9_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_V9.read_text(encoding="utf-8"))


def test_the_v9_fixture_is_a_real_render_at_version_9(v9_fixture: dict[str, Any]) -> None:
    """A genuine version 9 render, and now a superseded one."""
    assert v9_fixture["schema_version"] == 9
    assert v9_fixture["document_kind"] == "rendered"
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v9_fixture, "outputs.schema.json")

    migrated = output_migrations.migrate_v9_to_v10(
        v9_fixture, auth_connection_budget=auth_budget_for(v9_fixture)
    )
    assert migrated["schema_version"] == 10
    # Version 10 is no longer current, so the v9 fixture reaches a valid document
    # only through the v11 step as well. Asserted against a literal 10 above and
    # the constant below, deliberately: the fixture's own version is a fact about
    # a file and the chain's endpoint is a fact about this release, and writing
    # both as `CURRENT_VERSION` is how this assertion stopped meaning anything
    # the last time a version was added.
    migrated = output_migrations.migrate_v10_to_v11(
        migrated,
        storage_connection_budget=storage_budget_for(migrated),
        pooler_pool_size=pooler_pool_size_for(migrated),
        storage_route_url=storage_route_url_for(migrated),
        storage_settings=storage_settings_for(migrated),
    )
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v10_adds_the_auth_services_connection_budget(v9_fixture: dict[str, Any]) -> None:
    budget = auth_budget_for(v9_fixture)
    migrated = output_migrations.migrate_v9_to_v10(v9_fixture, auth_connection_budget=budget)

    assert migrated["schema_version"] == 10
    assert migrated["database"]["auth_connection_budget"] == budget
    # The API's is untouched: two claimants, two figures, and the step that adds
    # one must not quietly restate the other.
    assert (
        migrated["database"]["api_connection_budget"]
        == (v9_fixture["database"]["api_connection_budget"])
    )


def test_v10_refuses_a_budget_that_is_not_a_positive_integer(v9_fixture: dict[str, Any]) -> None:
    for value in (0, -1, "6", 6.0, None, True):
        with pytest.raises(MigrationError):
            output_migrations.migrate_v9_to_v10(v9_fixture, auth_connection_budget=value)


def test_v10_refuses_a_budget_that_leaves_the_application_nothing(
    v9_fixture: dict[str, Any],
) -> None:
    """The two services between them may not take the whole cluster.

    A document that renders and a deploy that fails is worse than a refusal: the
    failure lands in the bootstrap plane, where it reads as a cluster problem.
    """
    maximum = v9_fixture["database"]["budget"]["max_connections"]
    api = v9_fixture["database"]["api_connection_budget"]
    with pytest.raises(MigrationError, match="leaving nothing"):
        output_migrations.migrate_v9_to_v10(v9_fixture, auth_connection_budget=maximum - api)


def test_v10_refuses_a_document_that_already_carries_it(v9_fixture: dict[str, Any]) -> None:
    once = output_migrations.migrate_v9_to_v10(
        v9_fixture, auth_connection_budget=auth_budget_for(v9_fixture)
    )
    once["schema_version"] = 9
    with pytest.raises(MigrationError, match="already carries"):
        output_migrations.migrate_v9_to_v10(once, auth_connection_budget=6)


def test_v10_refuses_a_deployed_document(v9_fixture: dict[str, Any]) -> None:
    deployed = {**v9_fixture, "document_kind": "deployed"}
    with pytest.raises(MigrationError):
        output_migrations.migrate_v9_to_v10(deployed, auth_connection_budget=6)


def test_v10_does_not_mutate_its_input(v9_fixture: dict[str, Any]) -> None:
    before = json.dumps(v9_fixture, sort_keys=True)
    output_migrations.migrate_v9_to_v10(v9_fixture, auth_connection_budget=6)
    assert json.dumps(v9_fixture, sort_keys=True) == before


def test_the_renderer_and_the_migrator_agree_on_the_auth_budget(
    v9_fixture: dict[str, Any],
) -> None:
    """One authority for the figure (ADR 0002 applied to a number).

    `config.auth_connection_budget` is where the renderer gets it and what the
    manifest was checked against. If the two ever disagreed, a migrated document
    would publish a budget the bootstrap plane divides by and the manifest never
    approved -- and both halves would look right in isolation.
    """
    del v9_fixture
    assert config.auth_connection_budget({}) == (
        config.API_APP_DEFAULTS["pool_size"] + config.AUTH_RESERVED_CONNECTIONS
    )
    assert config.auth_connection_budget({"pool_size": 9}) == 9 + config.AUTH_RESERVED_CONNECTIONS


# ---------------------------------------------------------------------------
# v10 -> v11 (Session 7, ADR 0099)
# ---------------------------------------------------------------------------

#: The Session 6 render, produced by `deploy.sh --render-only` at commit
#: `d975800` -- Run 15, the last commit that still rendered version 10. Rendered
#: in a detached worktree rather than hand-built from `outputs-v9.json`, for the
#: reason every fixture in this module is a render: a document derived from the
#: migrator agrees with the migrator by construction and proves nothing about
#: what was shipped.
FIXTURE_V10 = REPO_ROOT / "tests" / "fixtures" / "outputs-v10.json"


@pytest.fixture
def v10_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_V10.read_text(encoding="utf-8"))


def v11_arguments(document: dict[str, Any]) -> dict[str, Any]:
    """Every version 11 argument, each from its own authority."""
    return {
        "storage_connection_budget": storage_budget_for(document),
        "pooler_pool_size": pooler_pool_size_for(document),
        "storage_route_url": storage_route_url_for(document),
        "storage_settings": storage_settings_for(document),
    }


def test_the_v10_fixture_is_a_real_render_at_version_10(v10_fixture: dict[str, Any]) -> None:
    """A genuine version 10 render, and now a superseded one.

    The second assertion is what makes the version bump mean something: if a v10
    document still validated, `schema_version` would be a label rather than a
    contract and an old reader would have no way to tell it was out of date.
    """
    assert v10_fixture["schema_version"] == 10
    assert v10_fixture["document_kind"] == "rendered"
    assert "storage_connection_budget" not in v10_fixture["database"]
    assert "storage" not in v10_fixture["routes"]
    with pytest.raises(config.ManifestError):
        config.validate_against_schema(v10_fixture, "outputs.schema.json")

    migrated = output_migrations.migrate_v10_to_v11(v10_fixture, **v11_arguments(v10_fixture))
    assert migrated["schema_version"] == 11
    # Version 11 is no longer current either, so a v10 fixture reaches a valid
    # document only through the v12 step as well. Written as a literal above and
    # the constant below for the reason the v9 test states in place: the step's
    # own result is a fact about that function, and the chain's endpoint is a
    # fact about this release. Spelling both `CURRENT_VERSION` is how this
    # assertion stopped meaning anything the last time a version was added, and
    # it is why this line had to be edited rather than merely re-run.
    migrated = output_migrations.migrate_v11_to_v12(migrated)
    assert migrated["schema_version"] == 12
    migrated = output_migrations.migrate_v12_to_v13(
        migrated,
        backup_bucket=backup_bucket_for(migrated),
        backup_retain_full=backup_retain_full_for(migrated),
        backup_network=backup_network_for(migrated),
    )
    assert migrated["schema_version"] == output_migrations.CURRENT_VERSION
    config.validate_against_schema(migrated, "outputs.schema.json")


def test_v11_adds_the_storage_budget_the_route_and_the_resolved_bounds(
    v10_fixture: dict[str, Any],
) -> None:
    """Four additions, one version, and D308 is why they arrive together.

    D255 is the record of the alternative: version 9 was chosen one run early
    with the session's remaining fields in mind and still missed the budget. A
    version is planned from the session's whole surface, not from the run in
    front of you.
    """
    arguments = v11_arguments(v10_fixture)
    migrated = output_migrations.migrate_v10_to_v11(v10_fixture, **arguments)

    assert migrated["schema_version"] == 11
    assert (
        migrated["database"]["storage_connection_budget"]
        == (arguments["storage_connection_budget"])
    )
    assert migrated["database"]["pooler_pool_size"] == arguments["pooler_pool_size"]
    assert migrated["routes"]["storage"] == arguments["storage_route_url"]
    for name, value in arguments["storage_settings"].items():
        assert migrated["storage"][name] == value

    # The three earlier claimants are untouched. A step that adds one must not
    # quietly restate the others -- that is how a figure the manifest approved
    # gets replaced by one nobody checked.
    for carried in ("api_connection_budget", "auth_connection_budget"):
        assert migrated["database"][carried] == v10_fixture["database"][carried]
    for carried in ("enabled", "bucket", "prefix"):
        assert migrated["storage"][carried] == v10_fixture["storage"][carried]


def test_v11_refuses_a_budget_that_is_not_a_positive_integer(v10_fixture: dict[str, Any]) -> None:
    """0 is 'reject every login' to PostgreSQL and a bool is an int in Python."""
    for field in ("storage_connection_budget", "pooler_pool_size"):
        for value in (0, -1, "6", 6.0, None, True):
            arguments = {**v11_arguments(v10_fixture), field: value}
            with pytest.raises(MigrationError):
                output_migrations.migrate_v10_to_v11(v10_fixture, **arguments)


def test_v11_refuses_a_budget_that_leaves_the_application_nothing(
    v10_fixture: dict[str, Any],
) -> None:
    maximum = v10_fixture["database"]["budget"]["max_connections"]
    api = v10_fixture["database"]["api_connection_budget"]
    auth = v10_fixture["database"]["auth_connection_budget"]
    arguments = {
        **v11_arguments(v10_fixture),
        "storage_connection_budget": maximum - api - auth,
    }
    with pytest.raises(MigrationError, match="leaving nothing"):
        output_migrations.migrate_v10_to_v11(v10_fixture, **arguments)


def test_v11_refuses_a_remainder_that_cannot_cover_the_poolers_pool(
    v10_fixture: dict[str, Any],
) -> None:
    """D327, checked where it can be checked without a cluster.

    **Paired with a control that differs in one field.** The control is the same
    call with the schema's own pool size, which must pass; the arm raises it to
    what the budget cannot cover. Without the control a passing test would not
    distinguish "refuses correctly" from "refuses everything", and a one-sided
    refusal is exactly the tautology D173 records.
    """
    control = v11_arguments(v10_fixture)
    output_migrations.migrate_v10_to_v11(v10_fixture, **control)

    maximum = v10_fixture["database"]["budget"]["max_connections"]
    committed = (
        v10_fixture["database"]["api_connection_budget"]
        + v10_fixture["database"]["auth_connection_budget"]
        + control["storage_connection_budget"]
    )
    arm = {**control, "pooler_pool_size": maximum - committed}
    with pytest.raises(MigrationError, match="pooler alone would not fit"):
        output_migrations.migrate_v10_to_v11(v10_fixture, **arm)


def test_v11_refuses_a_storage_route_it_would_have_to_derive(
    v10_fixture: dict[str, Any],
) -> None:
    """ADR 0002: this module derives no name, and says so rather than guessing.

    The route is `naming`'s. A migrator that built the URL from the document's
    domain and base path would be a second derivation of an address the render
    already owns, which is D177's shape.
    """
    for value in ("", "http://example.test/api/app/storage", "/api/app/storage", None, 7):
        arguments = {**v11_arguments(v10_fixture), "storage_route_url": value}
        with pytest.raises(MigrationError, match="https URL"):
            output_migrations.migrate_v10_to_v11(v10_fixture, **arguments)


def test_v11_refuses_a_partial_storage_block(v10_fixture: dict[str, Any]) -> None:
    """A missing bound leaves the service defaulting it, which is the second
    authority the resolution exists to remove."""
    complete = storage_settings_for(v10_fixture)
    for dropped in complete:
        partial = {name: value for name, value in complete.items() if name != dropped}
        arguments = {**v11_arguments(v10_fixture), "storage_settings": partial}
        with pytest.raises(MigrationError, match="missing"):
            output_migrations.migrate_v10_to_v11(v10_fixture, **arguments)


def test_v11_refuses_a_document_that_already_carries_it(v10_fixture: dict[str, Any]) -> None:
    once = output_migrations.migrate_v10_to_v11(v10_fixture, **v11_arguments(v10_fixture))
    once["schema_version"] = 10
    with pytest.raises(MigrationError, match="already carries"):
        output_migrations.migrate_v10_to_v11(once, **v11_arguments(v10_fixture))


def test_v11_refuses_a_deployed_document(v10_fixture: dict[str, Any]) -> None:
    deployed = {**v10_fixture, "document_kind": "deployed"}
    with pytest.raises(MigrationError):
        output_migrations.migrate_v10_to_v11(deployed, **v11_arguments(v10_fixture))


def test_v11_refuses_a_document_that_predates_version_10(v9_fixture: dict[str, Any]) -> None:
    """The step is chained, never jumped. A v9 document reaches 11 through 10."""
    with pytest.raises(MigrationError, match="only version 10"):
        output_migrations.migrate_v10_to_v11(v9_fixture, **v11_arguments(v9_fixture))


def test_v11_does_not_mutate_its_input(v10_fixture: dict[str, Any]) -> None:
    before = json.dumps(v10_fixture, sort_keys=True)
    output_migrations.migrate_v10_to_v11(v10_fixture, **v11_arguments(v10_fixture))
    assert json.dumps(v10_fixture, sort_keys=True) == before


def test_the_renderer_and_the_migrator_agree_on_the_storage_budget(
    v10_fixture: dict[str, Any],
) -> None:
    """One authority for the figure (ADR 0002 applied to a number).

    `config.storage_connection_budget` is where the renderer gets it and what
    the manifest was checked against. If the two ever disagreed, a migrated
    document would publish a budget the bootstrap plane divides by and the
    manifest never approved -- and both halves would look right in isolation.
    """
    del v10_fixture
    assert config.storage_connection_budget({}) == (
        config.STORAGE_DEFAULTS["pool_size"] + config.STORAGE_RESERVED_CONNECTIONS
    )
    assert config.storage_connection_budget({"pool_size": 9}) == (
        9 + config.STORAGE_RESERVED_CONNECTIONS
    )
