"""A project's own migration set: where it lives, what it may contain, how it is locked.

ADR 0198. `TEN-SET-001` and `TEN-SET-002`.

**What this module is for, in one sentence.** Until Session 20 an application
built on this appliance added its tables by editing seven files the release
tracks, one of which cannot be edited without a running host -- which is why
`DX-001` is answered *no* rather than left unattempted (ADR 0197). The set is the
repair, and this is what says the repair holds.

**The example set is the control throughout.** Every refusal below is measured
against a deliberately broken copy of `projects/example/` built under
`tmp_path`, and the real set is asserted to still pass in the same test. A lint
that refused everything would satisfy every refusal here and be useless; a lint
that refused nothing would satisfy none of them. Both directions are checked
because only one of them is the failure that ships.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface, migrations, rendering, sql_surface

pytestmark = [pytest.mark.contract, pytest.mark.p0]

EXAMPLE = REPO_ROOT / "projects" / "example"
FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"
SECOND_FIXTURE = REPO_ROOT / ".generated" / "fixture-alpine-dev"


@pytest.fixture
def example() -> migrations.MigrationSet:
    return migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")


@pytest.fixture
def document() -> dict[str, Any]:
    """The rendered document of the project that declares a set."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    return json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))


@pytest.fixture
def setless_document() -> dict[str, Any]:
    """The control: a project at the same schema version with NO set.

    `project.second.example.yaml` is version 5 and declares no `migrations`
    block, so every assertion about a set below has a same-version project
    beside it that has none. Without this pair, "a set renders" and "schema 5
    renders" would be one measurement.
    """
    if not (SECOND_FIXTURE / "outputs.json").is_file():
        pytest.skip("no second rendered fixture; run ./deploy.sh --render-only")
    return json.loads((SECOND_FIXTURE / "outputs.json").read_text(encoding="utf-8"))


@pytest.fixture
def copied(tmp_path: Path) -> Path:
    """A writable copy of the example set. The committed one is never edited."""
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root)
    return root


def broken(root: Path, target: str, anchor: str, replacement: str) -> migrations.MigrationSet:
    """One mutation, with its anchor pre-flighted to match exactly once (D269).

    A mutation whose anchor misses is applied to nothing, and a lint that then
    accepts the file reports as a lint that refuses nothing. That is the single
    most common way a refusal test becomes vacuous, so the miss is fatal here
    rather than a skipped arm.
    """
    path = root / target
    text = path.read_text(encoding="utf-8")
    assert text.count(anchor) == 1, (
        f"the anchor {anchor!r} matches {text.count(anchor)} times in {target}, not once; "
        "nothing was mutated and any refusal below would be measuring the wrong thing"
    )
    path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
    return migrations.MigrationSet(label="project", root=root / "migrations")


TEMPLATE = "migrations/templates/0001-note-embeddings.sql"
MANIFEST = "migrations/manifest.json"
PREAMBLE = "SET LOCAL ROLE {{object_owner}};"


# ---------------------------------------------------------------------------
# TEN-SET-001 -- where the set lives, and how it is ordered and locked
# ---------------------------------------------------------------------------


def test_a_declared_set_renders_after_the_release_set_in_version_order(
    document: dict[str, Any], setless_document: dict[str, Any]
) -> None:
    """The release's set, then the project's, in one directory.

    dbmate is handed a DIRECTORY and orders the whole of it by filename, which
    is why this is asserted about versions rather than about the order
    `sets_for` returns. Rig 20a measured what the difference costs: with an
    out-of-order pending migration, `up --strict` exits 2 having applied nothing
    on a deployed cluster, while a fresh cluster applies the same pair silently
    -- one set producing two schemas (D1098).

    The setless project is the control, in the same test: it must render the
    release's set alone, or "the release comes first" would be trivially true of
    a list with one thing in it.
    """
    sets = migrations.sets_for(document)
    assert [migration_set.label for migration_set in sets] == ["release", "project"]

    release_versions = [entry["version"] for entry in sets[0].load_manifest()["migrations"]]
    project_versions = [entry["version"] for entry in sets[1].load_manifest()["migrations"]]
    assert release_versions and project_versions
    assert min(project_versions) > max(release_versions), (
        "a project migration sorts before a release migration, so dbmate would "
        "apply them in a different order than sets_for describes"
    )

    control = migrations.sets_for(setless_document)
    assert [migration_set.label for migration_set in control] == ["release"], (
        "the control project declares no set and got one anyway"
    )


def test_the_project_lock_is_frozen_and_verified_apart_from_the_release_lock(
    example: migrations.MigrationSet,
) -> None:
    """Two locks, each verified against its own manifest and templates.

    The release's lock is not a per-project artifact (ADR 0028) and a project's
    is not the release's. What this asserts is that neither covers the other:
    the release lock records no project version, and the project lock records no
    release version. A lock that covered both would make `verify_lock` pass for
    a project whose set had been swapped for the release's.
    """
    release = migrations.release_set()
    release_lock = release.load_lock()
    project_lock = example.load_lock()

    assert release_lock["schema_version"] == 1
    assert project_lock["schema_version"] == 2
    assert "follows_release_version" not in release_lock, (
        "the release lock grew a project field, so the version rule would apply "
        "to the release's own migrations"
    )
    assert "follows_release_version" in project_lock

    release_versions = {entry["version"] for entry in release_lock["migrations"]}
    project_versions = {entry["version"] for entry in project_lock["migrations"]}
    assert release_versions and project_versions
    assert not (release_versions & project_versions)

    # Each verifies against its own manifest and root, and this is the assertion
    # that would go red if either lock were stale.
    migrations.verify_lock(release.load_manifest(), release_lock, release.root)
    migrations.verify_lock(example.load_manifest(), project_lock, example.root)


def test_a_project_version_older_than_the_release_lock_is_refused(copied: Path) -> None:
    """The freeze-time refusal in front of dbmate's deploy-time one.

    Both boundaries: a version strictly older than the recorded release version,
    and a version EQUAL to it. Equal is refused because the rule is "sorts
    after", and two migrations sharing a version would give dbmate one ledger
    key for two files.

    The control is the same set with its real version, verified in the same
    test -- otherwise a `verify_lock` that raised unconditionally would satisfy
    both arms.
    """
    follows = migrations.newest_release_version()
    manifest_path = copied / MANIFEST

    for version, why in (("20260903000000", "older"), (follows, "equal")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["migrations"][0]["version"] = version
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        candidate = migrations.MigrationSet(label="project", root=copied / "migrations")
        built = migrations.build_lock(
            candidate.load_manifest(), candidate.root, follows_release_version=follows
        )
        with pytest.raises(migrations.ProjectSetError, match="do not sort after"):
            migrations.verify_lock(candidate.load_manifest(), built, candidate.root)
        assert why  # the label is for the failure message, not the logic

    # The control, in the same invocation (D499).
    real = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    migrations.verify_lock(real.load_manifest(), real.load_lock(), real.root)


def test_the_release_lock_is_never_rewritten_by_a_project_freeze() -> None:
    """`freeze-lock --project` writes one file and it is not the release's.

    Asserted from the SOURCE of `bin/migrate.py` rather than by running the verb
    against the real tree, because the only convincing way to run it would be to
    let it write -- and a test that proves a file is untouched by touching it is
    not the test it looks like.
    """
    source = (REPO_ROOT / "bin" / "migrate.py").read_text(encoding="utf-8")
    body = source.split("def freeze_project_lock(", 1)[1].split("\ndef ", 1)[0]
    assert "migration_set.lock_path.write_text" in body
    assert "migrations.LOCK_PATH" not in body, (
        "the project freeze names the release's lock path; the release's lock is "
        "not a project's to write (ADR 0028)"
    )


def test_the_project_set_lives_in_the_checkout_and_not_beside_the_host_manifest() -> None:
    """D1087. The schema constrains the shape; this asserts the tree agrees.

    A release is exactly the commit it is named for: `assert_clean` refuses a
    dirty checkout, the deploy runs the checked-out release's `migrate.sh`, and
    `upgrade plan` diffs two rendered releases. SQL living beside a manifest on
    the host would be applied by a release that does not contain it -- a schema
    no commit determines.
    """
    assert (EXAMPLE / "migrations" / "manifest.json").is_file()
    assert (EXAMPLE / "migrations" / "released.lock.json").is_file()
    assert list((EXAMPLE / "migrations" / "templates").glob("*.sql"))
    assert EXAMPLE.relative_to(REPO_ROOT).parts[0] == migrations.PROJECT_SETS_DIRECTORY


# ---------------------------------------------------------------------------
# TEN-SET-002 -- the lint
# ---------------------------------------------------------------------------

FORBIDDEN = [
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nGRANT USAGE ON SCHEMA app_private TO {{authenticated}};",
        "app_private",
        id="names_app_private",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nCREATE ROLE tenant_writer NOLOGIN;",
        "creates or alters a role",
        id="creates_a_role",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nCREATE SCHEMA tenant;",
        "creates or alters a schema",
        id="creates_a_schema",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nCREATE EXTENSION postgis;",
        "creates or alters an extension",
        id="creates_an_extension",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nALTER DEFAULT PRIVILEGES IN SCHEMA api GRANT ALL ON TABLES TO PUBLIC;",
        "alters default privileges",
        id="alters_default_privileges",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        "SET ROLE {{object_owner}};",
        "sets a role other than the owner preamble",
        id="set_role_not_local",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nDROP VIEW api.notes;",
        "drops api.notes",
        id="drops_a_release_view",
    ),
    pytest.param(
        TEMPLATE,
        PREAMBLE,
        PREAMBLE + "\nDROP FUNCTION api.create_note;",
        "drops api.create_note",
        id="drops_a_release_function",
    ),
    pytest.param(
        TEMPLATE,
        "ALTER TABLE app.note_embeddings FORCE ROW LEVEL SECURITY;",
        "",
        "without FORCE ROW LEVEL SECURITY",
        id="table_in_app_without_force_rls",
    ),
    pytest.param(
        TEMPLATE,
        "RAISE EXCEPTION 'AP900: this migration plane is fix-forward only'",
        "RAISE EXCEPTION 'rolled back'",
        "does not raise AP900",
        id="down_block_that_rolls_back",
    ),
    pytest.param(
        MANIFEST,
        '"source": "database.roles.authenticated"',
        '"source": "database.roles.app_runtime"',
        "which a project set may not read",
        id="placeholder_outside_the_allowlist",
    ),
]


@pytest.mark.parametrize("target,anchor,replacement,message", FORBIDDEN)
def test_the_lint_refuses_each_forbidden_shape_and_accepts_the_example_set(
    copied: Path,
    example: migrations.MigrationSet,
    target: str,
    anchor: str,
    replacement: str,
    message: str,
) -> None:
    """One arm per forbidden shape, with the real set as the control.

    The control is asserted in EVERY arm rather than once in a test of its own,
    and that is deliberate (D499): a mutation is evidence only beside a control
    the mutation cannot reach, run in the same invocation. A lint that started
    raising unconditionally would pass every refusal arm and be caught here.
    """
    candidate = broken(copied, target, anchor, replacement)
    with pytest.raises(migrations.ProjectSetError, match=message):
        migrations.lint_project_set(candidate)

    migrations.lint_project_set(example)


def test_the_lint_reads_statements_and_not_comments(copied: Path) -> None:
    """A forbidden word inside a comment is not a forbidden statement.

    Session 2 Run 7's defect exactly -- a substitution that also matched the
    comment documenting the substitution -- and the reason `sql_surface.sql_only`
    exists. Without this, the honest thing to do about `app_private` in a
    template's prose would be to stop explaining why it is forbidden.
    """
    candidate = broken(
        copied,
        TEMPLATE,
        PREAMBLE,
        "-- This set may not reach app_private, and CREATE ROLE is refused.\n" + PREAMBLE,
    )
    migrations.lint_project_set(candidate)


def test_the_lint_refuses_a_set_with_no_down_block_at_all(copied: Path) -> None:
    """Not merely a `down` that rolls back -- a template with no down section.

    dbmate treats a missing section as an empty one and reports success, so the
    absence is the more dangerous of the two states and the one a reader is less
    likely to look for.
    """
    path = copied / TEMPLATE
    text = path.read_text(encoding="utf-8")
    path.write_text(text.split(sql_surface.DOWN_MARKER)[0], encoding="utf-8")
    candidate = migrations.MigrationSet(label="project", root=copied / "migrations")
    with pytest.raises(migrations.ProjectSetError, match="has no"):
        migrations.lint_project_set(candidate)


def test_the_lint_is_not_vacuous_on_the_example_set(example: migrations.MigrationSet) -> None:
    """The example set reaches every rule rather than passing them by absence.

    A lint whose rules are all about statements a set does not contain is a lint
    the set passes trivially. The example set creates a table in `app`, publishes
    a view and a function in `api`, sets the owner preamble, declares
    placeholders and carries a `down` block -- so each refusal above has
    something in the control it could have fired on and did not.
    """
    manifest = example.load_manifest()
    text = (example.root / manifest["migrations"][0]["template"]).read_text(encoding="utf-8")
    applied = sql_surface.statements(text)

    assert "CREATE TABLE app." in applied
    assert "FORCE ROW LEVEL SECURITY" in applied
    assert migrations.PROJECT_ROLE_PREAMBLE in applied
    assert manifest["placeholders"]
    assert migrations.PROJECT_DOWN_SENTINEL in sql_surface.sql_only(sql_surface.down_section(text))


def test_every_placeholder_the_example_set_declares_is_in_the_allowlist(
    example: migrations.MigrationSet,
) -> None:
    """And the allowlist names no platform identity.

    The second assertion is the one with teeth: a future widening that added
    `app_runtime` or `migration_user` to the allowlist would leave every lint
    test above green, because none of them names a source the allowlist forbids
    -- they name one it forbids TODAY.
    """
    declared = {
        specification["source"]
        for specification in example.load_manifest()["placeholders"].values()
    }
    assert declared <= migrations.PROJECT_PLACEHOLDER_SOURCES

    forbidden = {
        "database.roles.app_runtime",
        "database.roles.migration_user",
        "database.roles.backup_user",
        "database.roles.auth_service",
        "database.roles.storage_service",
        "database.roles.mcp_audit_service",
        "database.roles.postgrest_authenticator",
        "database.roles.project_admin",
        "database.container",
    }
    assert not (migrations.PROJECT_PLACEHOLDER_SOURCES & forbidden), (
        "the allowlist names a platform identity; a project's SQL has no business "
        "naming one, and every lint arm above would stay green if it did"
    )


# ---------------------------------------------------------------------------
# The reader, over a project's own set
# ---------------------------------------------------------------------------


def test_the_project_reader_finds_the_objects_the_example_set_publishes(
    example: migrations.MigrationSet,
) -> None:
    """`sql_surface` over a project's set, non-empty, naming what the SQL names.

    The anti-vacuity assertion belongs on both sides. The release's reader keeps
    its equality against `{"notes","tasks"}` because a project's objects are in
    the project's files (D1089); this is the same property for the other half,
    and without it a regex that matched nothing here would make every project
    comparison hold against two empty sets.
    """
    surface = sql_surface.final_surface(example.load_manifest(), example.root)
    assert sql_surface.published_names(surface), "the reader found no project objects at all"
    assert set(surface["views"]) == {"note_embeddings"}
    assert set(surface["functions"]) == {"set_note_embedding"}


def test_the_release_reader_never_sees_a_projects_object() -> None:
    """D1089, as an assertion rather than as a claim in a plan.

    This is what makes the release's anti-vacuity guard safe to leave alone. If
    a project's objects could reach the release's reader, that guard's equality
    against `{"notes","tasks"}` would have to be loosened to a containment check
    for every adopter -- which the non-negotiables call weakening.
    """
    release = migrations.release_set()
    release_names = sql_surface.published_names(
        sql_surface.final_surface(release.load_manifest(), release.root)
    )
    example = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    project_names = sql_surface.published_names(
        sql_surface.final_surface(example.load_manifest(), example.root)
    )

    assert project_names, "the example set publishes nothing, so this proves nothing"
    assert not (release_names & project_names)
    assert "note_embeddings" not in release_names


def test_a_project_may_not_publish_a_name_the_release_owns(copied: Path) -> None:
    """Two objects with one name in one schema is one object, and a silent one.

    `CREATE OR REPLACE VIEW api.notes` in a project's set would replace the
    release's view with the project's, on a deployed cluster, with the release's
    reviewed contract still describing the old one.
    """
    candidate = broken(
        copied,
        TEMPLATE,
        "CREATE VIEW api.note_embeddings",
        "CREATE VIEW api.notes",
    )
    release = migrations.release_set()
    release_names = sql_surface.published_names(
        sql_surface.final_surface(release.load_manifest(), release.root)
    )
    project_names = sql_surface.published_names(
        sql_surface.final_surface(candidate.load_manifest(), candidate.root)
    )
    assert release_names & project_names == {"notes"}, (
        "the collision this test exists to describe did not happen, so a "
        "refusal built on it would be measuring nothing"
    )


# ---------------------------------------------------------------------------
# The rendered document
# ---------------------------------------------------------------------------


def test_the_rendered_document_records_the_set_it_applied(
    document: dict[str, Any], setless_document: dict[str, Any]
) -> None:
    """TEN-DOC-001's offline half, on both branches of the pair.

    The digest is of the LOCK's bytes, not the manifest's: the lock is what
    `verify_lock` compares and what a reviewer approved, so the document says
    "this deployment applied the set somebody reviewed" rather than "the set
    somebody described".
    """
    block = document["migrations"]
    assert block["release_lock_sha256"]
    assert block["project_set"]["root"] == "projects/example"

    # The count is compared against the lock rather than written here as a
    # literal. It was 1 until D1156's grant arrived as a second migration, and a
    # literal has to be edited every time the worked example grows -- which is
    # how a count quietly stops being checked. The floor below keeps the
    # assertion from becoming "the document agrees with itself".
    recorded = json.loads(
        (EXAMPLE / "migrations" / "released.lock.json").read_text(encoding="utf-8")
    )
    assert block["project_set"]["count"] == len(recorded["migrations"])
    assert block["project_set"]["count"] >= 2, (
        "the example set has carried two migrations since D1156; a document that "
        "reports fewer was rendered against a lock this checkout does not have"
    )

    from hashlib import sha256

    expected = sha256((EXAMPLE / "migrations" / "released.lock.json").read_bytes()).hexdigest()
    assert block["project_set"]["lock_sha256"] == expected

    control = setless_document["migrations"]
    assert control["project_set"] is None, (
        "the control project declares no set and its document names one"
    )
    assert control["release_lock_sha256"] == block["release_lock_sha256"], (
        "two projects rendered by one release disagree about the release lock"
    )


def test_project_set_from_reads_the_document_and_not_the_manifest(
    document: dict[str, Any],
) -> None:
    """ADR 0002. One authority for a derived fact.

    A reader that went back to `project.example.yaml` would be a second
    derivation path with the same failure mode ADR 0023 records -- and would
    answer for the checkout it is sitting in rather than for the deployment.
    """
    stripped = copy.deepcopy(document)
    del stripped["migrations"]
    assert migrations.project_set_from(stripped) is None, (
        "the set was found in a document that does not name one, so something "
        "other than the document supplied it"
    )
    assert migrations.project_set_from(document) is not None


def test_the_project_reader_finds_every_object_the_project_contract_names() -> None:
    """TEN-SURF-001, over EVERY set in `projects/`, not just the example's.

    ADR 0050's invariant for a project: nothing exists in `api` which that
    project's reviewed contract does not name, and nothing is named which the
    SQL does not create. Both directions, because each catches a different
    mistake -- an object added to a migration and not to the contract is an
    unreviewed publication, and one added to the contract and not to a migration
    is a contract describing a catalog that does not exist.

    Parameterised over the directory rather than over a list of slugs, so a
    second example set added later is covered without anybody remembering to
    add it. The non-empty assertion is what stops that from silently becoming a
    loop over nothing.
    """
    roots = sorted(
        path
        for path in (REPO_ROOT / "projects").iterdir()
        if path.is_dir() and (path / "migrations" / "manifest.json").is_file()
    )
    assert roots, "there are no project sets in projects/, so this loop proves nothing"

    for root in roots:
        contract = api_surface.load_project_surface(api_surface.project_contract_path(root))
        migration_set = migrations.MigrationSet(label="project", root=root / "migrations")
        surface = sql_surface.final_surface(migration_set.load_manifest(), migration_set.root)

        published = sql_surface.published_names(surface)
        assert published, f"{root.name}: the reader found no objects in this project's SQL"

        named = set(contract["relations"]) | set(contract["rpcs"]) | set(contract["enums"])
        assert named, f"{root.name}: the contract names nothing"

        assert published == named, (
            f"{root.name}: the SQL publishes {sorted(published)} and the contract names "
            f"{sorted(named)}. An object in the migrations and not the contract is an "
            "unreviewed publication; one in the contract and not the migrations is a "
            "contract describing a catalog that does not exist."
        )

        # And the columns, for every relation. The names agreeing is the cheap
        # half: a view whose column list drifted from its contract publishes a
        # field nobody reviewed, under a relation name somebody did.
        for name, declared in contract["relations"].items():
            assert surface["views"][name] == declared["columns"], (
                f"{root.name}: api.{name} selects {surface['views'][name]} and the "
                f"contract names {declared['columns']}"
            )

        for name, declared in contract["rpcs"].items():
            assert surface["functions"][name] == declared["arguments"], (
                f"{root.name}: api.{name} takes {surface['functions'][name]} and the "
                f"contract names {declared['arguments']} -- and these strings are the "
                "wire format, because PostgREST maps JSON body keys onto parameter names"
            )


def test_a_project_set_that_publishes_nothing_is_caught_by_the_reader(
    copied: Path,
) -> None:
    """The arm the loop above cannot reach, and the reason it needed one.

    `test_the_project_reader_finds_every_object_the_project_contract_names`
    walks the sets that exist in `projects/`, and all of them publish something
    -- so its `assert published` guard never fires and a battery mutation
    removing that guard SURVIVED. A guard with no scenario is not a guard.

    Here the set's migration keeps its table and loses its view and its
    function, which is the realistic shape: a tenant adds storage in one
    migration and the published surface in the next, and between the two their
    contract names objects the SQL does not create. The reader must report an
    empty surface rather than an agreeing one -- because `published == named`
    holds trivially when both sides are empty, and that is the comparison this
    whole file rests on.
    """
    path = copied / TEMPLATE
    text = path.read_text(encoding="utf-8")
    applied, marker, down = text.partition(sql_surface.DOWN_MARKER)

    # Everything from the view onward, out. The table, its row security and its
    # policy stay: this is a set that stores and publishes nothing.
    cut = applied.index("CREATE VIEW api.note_embeddings")
    path.write_text(applied[:cut] + "RESET ROLE;\n" + marker + down, encoding="utf-8")

    # The request-role placeholders go with the objects they granted on, and
    # **so does the second migration**: `20260914120002` grants on the view
    # `20260914120001` publishes, so a set whose first migration stops
    # publishing it cannot keep a second that grants on it. Dropping both is
    # what an adopter making this change would have to do, which is the point --
    # the arm has to be a set that could EXIST, or it measures the manifest
    # rules rather than the reader.
    #
    # `load_manifest` refuses a declaration whose template never uses it, and
    # that refusal is right: a stale placeholder reads to the next person as
    # evidence that the value still reaches the migration.
    manifest_path = copied / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["migrations"][1:]:
        (copied / "migrations" / entry["template"]).unlink()
    manifest["migrations"] = manifest["migrations"][:1]
    manifest["migrations"][0]["placeholders"] = ["object_owner"]
    for name in ("authenticated", "api_documentation", "agent_reader", "agent_writer"):
        manifest["placeholders"].pop(name, None)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    migration_set = migrations.MigrationSet(label="project", root=copied / "migrations")
    surface = sql_surface.final_surface(migration_set.load_manifest(), migration_set.root)
    published = sql_surface.published_names(surface)

    assert published == set(), (
        f"the reader found {sorted(published)} in a set whose view and function were "
        "removed, so it is reading something other than this set's SQL"
    )

    # And the comparison the loop makes is what catches it: the contract still
    # names two objects the SQL no longer creates.
    contract = api_surface.load_project_surface(api_surface.project_contract_path(copied))
    named = set(contract["relations"]) | set(contract["rpcs"]) | set(contract["enums"])
    assert named, "the contract names nothing, so the disagreement below is not one"
    assert published != named

    # The control, in the same test (D499): the committed set still publishes.
    real = migrations.MigrationSet(label="project", root=EXAMPLE / "migrations")
    real_surface = sql_surface.final_surface(real.load_manifest(), real.root)
    assert sql_surface.published_names(real_surface)


def test_the_example_lock_records_two_migrations_in_order(
    example: migrations.MigrationSet,
) -> None:
    """The set is fix-forward, so D1156's grant arrived as a second migration.

    20260914120001 is frozen and applied on beta; a grant added by editing it
    would be an amended applied migration (D912). So the lock must carry two
    entries, in version order, both sorting after `follows_release_version` --
    which dbmate needs, because it is handed one directory and orders the whole
    of it by filename (D1098).

    `follows_release_version` moved from 20260904120030 to 20260912120031 when
    this set was re-frozen: `freeze-lock` recomputes it from the release lock's
    newest, and migration 0031 (`api.create_task`, ADR 0196) shipped after this
    set was first frozen. Both of this set's versions still sort after it, which
    is the property the field exists for, and that is asserted below rather than
    the literal (D1180).

    Goes red if: the second migration is dropped or renamed, the two are frozen
    out of order, a version is stamped before the release's newest, or a
    template digest stops matching the file the manifest names.
    """
    lock = example.load_lock()
    manifest = example.load_manifest()

    versions = [entry["version"] for entry in lock["migrations"]]
    assert versions == ["20260914120001", "20260914120002"], (
        f"the example set's lock records {versions}; the grant migration D1156 needs "
        "is a SECOND entry, because the first is frozen and applied"
    )
    assert versions == sorted(versions), "the lock records the set out of version order"
    assert versions == [entry["version"] for entry in manifest["migrations"]], (
        "the lock and the manifest disagree about which migrations this set has"
    )

    follows = lock["follows_release_version"]
    assert min(versions) > follows, (
        f"{min(versions)} sorts before the release's newest ({follows}), so dbmate "
        "would apply this set's SQL before the release's on a fresh cluster and "
        "refuse it with exit 2 on a deployed one (D1098)"
    )

    # The digest is what makes the entry a freeze rather than a note.
    for entry in lock["migrations"]:
        template = (example.root / entry["template"]).read_text(encoding="utf-8")
        assert entry["template_sha256"] == hashlib.sha256(template.encode("utf-8")).hexdigest(), (
            f"{entry['template']} does not digest to what the lock records for it"
        )

    # The control, in the same test: the release's own lock still records its
    # own set and knows nothing about this one.
    release = migrations.release_set().load_lock()
    assert not {entry["version"] for entry in release["migrations"]} & set(versions), (
        "a project version appears in the release lock, so `freeze-lock --project` "
        "wrote the release's lock as well as the project's"
    )


# ---------------------------------------------------------------------------
# ADR 0206: the two sets are ordered independently
# ---------------------------------------------------------------------------


def test_a_release_version_below_an_applied_project_version_is_no_longer_refused() -> None:
    """D1288, as a unit, with the exact interleaving that stopped beta's deploy.

    Release `20260912120032` sorts BELOW the project's applied `20260914120001`,
    because the release stamps by authoring date and the example project's set
    was stamped two days ahead of the release's clock to clear
    `follows_release_version`. While the two sets shared a directory and a table
    this was a render error and then, on a deployed cluster, an `up --strict`
    refusal that applied nothing.

    Each set now has its own directory and its own table, so the interleaving is
    legal and this must NOT raise. The committed manifests cannot express this
    case without being edited, which is why the rule is a function taking
    entries rather than a check inside the render.
    """
    entries = [
        {"version": "20260912120031", "set": "release"},
        {"version": "20260912120032", "set": "release"},
        {"version": "20260914120001", "set": "project"},
        {"version": "20260914120002", "set": "project"},
    ]
    rendering.assert_migration_order(entries)

    # And the other direction, which is the shape D1288 actually produced: a
    # release version authored AFTER the project's and stamped below it.
    rendering.assert_migration_order(
        [
            {"version": "20260914120001", "set": "project"},
            {"version": "20260914120002", "set": "project"},
            {"version": "20260912120032", "set": "release"},
        ]
    )


def test_a_set_whose_own_versions_do_not_ascend_is_still_refused() -> None:
    """The control. Within a set the order is still dbmate's, and still checked.

    Without this the proof above would be satisfied by a rule that checks
    nothing at all -- which is the easy way to make a cross-set constraint go
    away and the reason this pair exists.
    """
    with pytest.raises(rendering.RenderError) as raised:
        rendering.assert_migration_order(
            [
                {"version": "20260912120032", "set": "release"},
                {"version": "20260912120031", "set": "release"},
            ]
        )
    assert "ascending version order" in str(raised.value)


def test_two_sets_may_not_share_a_version_even_with_separate_tables() -> None:
    """The tables would tolerate it; `migration_ledger` would not.

    It keys on the version alone and is written `ON CONFLICT (version) DO
    NOTHING`, so a shared version applies twice and is recorded once -- and the
    ledger is the one record of which bytes ran (D1096). The reason changed
    with ADR 0206; the rule did not.
    """
    with pytest.raises(rendering.RenderError) as raised:
        rendering.assert_migration_order(
            [
                {"version": "20260914120001", "set": "release"},
                {"version": "20260914120001", "set": "project"},
            ]
        )
    assert "share a version" in str(raised.value)
    assert "migration_ledger" in str(raised.value)


def test_each_set_is_rendered_into_its_own_directory_and_names_its_own_table() -> None:
    """The layout the two dbmate services are pointed at (ADR 0206)."""
    manifest = json.loads(
        (FIXTURE / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    by_set: dict[str, set[str]] = {}
    for entry in manifest["migrations"]:
        by_set.setdefault(entry["set"], set()).add(entry["dir"])

    assert by_set == {
        "release": {rendering.RELEASE_MIGRATIONS_SUBDIR},
        "project": {rendering.PROJECT_MIGRATIONS_SUBDIR},
    }, f"a set is rendered into more than one directory: {by_set}"

    assert manifest["migrations_table"] == rendering.MIGRATIONS_TABLE
    assert manifest["project_migrations_table"] == rendering.PROJECT_MIGRATIONS_TABLE
    assert rendering.MIGRATIONS_TABLE != rendering.PROJECT_MIGRATIONS_TABLE, (
        "one table is one ordering space, which is the whole of D1288"
    )

    for subdir in (rendering.RELEASE_MIGRATIONS_SUBDIR, rendering.PROJECT_MIGRATIONS_SUBDIR):
        on_disk = {path.name for path in (FIXTURE / subdir).glob("*.sql")}
        recorded = {e["file"] for e in manifest["migrations"] if e["dir"] == subdir}
        assert on_disk == recorded, f"{subdir}: {sorted(on_disk ^ recorded)}"


def test_the_move_takes_the_project_versions_and_only_those() -> None:
    """D1288's repair, read as SQL before it is ever run on a cluster.

    A cluster migrated before ADR 0206 recorded both sets in one table, so the
    release's `max(applied)` includes project versions -- which is what refused
    beta. The move is driven by the rendered manifest, so it names exactly the
    versions this release rendered as a project's.
    """
    statement = migrations.project_ledger_move_statement(FIXTURE)
    assert statement is not None

    project_versions = [
        entry["version"]
        for entry in json.loads(
            (FIXTURE / "migrations" / rendering.MIGRATION_MANIFEST_NAME).read_text(encoding="utf-8")
        )["migrations"]
        if entry["set"] == "project"
    ]
    assert project_versions, "the fixture declares no project set; this proves nothing"

    for version in project_versions:
        assert f"'{version}'" in statement
    # And no release version is swept along with them.
    release_versions = [
        entry["version"] for entry in migrations.release_set().load_manifest()["migrations"]
    ]
    for version in release_versions:
        assert f"'{version}'" not in statement, f"the move names release version {version}"

    assert statement.startswith("BEGIN;"), "a delete that outlived its insert would lose a record"
    assert statement.rstrip().endswith("COMMIT;")
    assert "ON CONFLICT (version) DO NOTHING" in statement, "the move must be re-runnable"
    assert rendering.MIGRATIONS_TABLE in statement
    assert rendering.PROJECT_MIGRATIONS_TABLE in statement


def test_a_project_with_no_set_is_moved_nothing_at_all() -> None:
    """The control, and the case nearly every project is in.

    `None` rather than an empty transaction: the caller issues nothing, so a
    project with no set reaches no psql at all and cannot fail in a path that
    has no work to do for it.
    """
    assert migrations.project_ledger_move_statement(SECOND_FIXTURE) is None


# ---------------------------------------------------------------------------
# What the ADOPTER sees when their own set is refused (Session 25, rig 25i)
# ---------------------------------------------------------------------------


def _render_config_module():
    """`bin/render-config.py`, imported by path and REGISTERED in `sys.modules`.

    Registration matters for any module that builds a dataclass at import time
    (`@dataclass` resolves `sys.modules[cls.__module__]` while the class is
    created), and it costs nothing here.
    """
    import importlib.util
    import sys

    name = "_render_config_under_test"
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "bin" / "render-config.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_render_reports_a_project_sets_refusal_instead_of_a_stack(monkeypatch, capsys) -> None:
    """**Measured before it was fixed** (rig 25i, 2026-09-14).

    A project migration stamped below the version its set was frozen against,
    and a table in `app` without FORCE row level security, are the two refusals
    an adopter is most likely to meet. `write_rendered_migrations` calls
    `verify_lock`, which raises `ProjectSetError` -- a `MigrationError`, which is
    a `ValueError` and is **not** a `RenderError`. `bin/render-config.py` caught
    `RenderError`, `ManifestError` and `CapabilityContractError`, so both
    escaped: `./deploy.sh --render-only` printed a Python traceback and exited
    **1**, a code the exit-code convention does not define.

    `bin/migrate.py` and `bin/dev.py` had handled this class since Session 20.
    The render is the third caller of the same function and it did not, which is
    D979 and §7's fifth question: when a decision is implemented, which of its
    callers got it.

    Three arms, because a handler that returns 5 for everything is worse than
    the traceback: the project error is reported, the `RenderError` branch that
    already existed still is, and an unrelated exception still propagates rather
    than being swallowed into a contract exit code.
    """
    module = _render_config_module()
    project = REPO_ROOT / "project.example.yaml"
    capabilities = REPO_ROOT / "capabilities.example.yaml"

    # The anti-vacuity check: the name being replaced is the real one.
    assert callable(module.rendering.render_project), (
        "render-config no longer calls rendering.render_project, so this proof is "
        "monkeypatching something the command does not use"
    )

    sentence = "do not sort after the release version this set was frozen against"

    def refuse_the_set(*_args, **_kwargs):
        raise migrations.ProjectSetError(f"these project migrations {sentence} (20260912120032)")

    monkeypatch.setattr(module.rendering, "render_project", refuse_the_set)
    code = module.render(project, capabilities)
    printed = capsys.readouterr().err
    assert code == 5, f"a refused project set exited {code}, not 5"
    assert sentence in printed, f"the refusal was not reported: {printed!r}"
    assert "Traceback" not in printed, "the refusal reached the operator as a stack"

    # The branch that already existed, unchanged.
    def refuse_the_render(*_args, **_kwargs):
        raise module.rendering.RenderError("the staged model does not validate")

    monkeypatch.setattr(module.rendering, "render_project", refuse_the_render)
    assert module.render(project, capabilities) == 5
    assert "does not validate" in capsys.readouterr().err

    # And the control: the new clause is not a blanket `except Exception`.
    def something_else(*_args, **_kwargs):
        raise RuntimeError("a defect in the renderer, not a refusal of the input")

    monkeypatch.setattr(module.rendering, "render_project", something_else)
    with pytest.raises(RuntimeError, match="a defect in the renderer"):
        module.render(project, capabilities)
