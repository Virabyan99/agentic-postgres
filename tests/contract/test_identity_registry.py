"""Migration 0011, the identity registry (ADR 0080, D218).

Read from the template's source. What the migration *does* was measured against
the locked image before it was written -- all eleven applied in order, and every
constraint refused what it exists for with a control beside it -- and that rig is
not reproducible in an offline suite. What is reproducible, and what these
assertions are for, is that the source keeps saying the things the measurement
was about.

The one that matters most is the NULL clause. `is_scope_set` without its
`coalesce` accepted `ARRAY['a', NULL]` on a real cluster, because a CHECK
constraint passes when its expression is NULL. That is not visible by reading
unless somebody knows to look, so it is asserted here by name.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, jwt_claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

TEMPLATE_PATH = REPO_ROOT / "migrations" / "templates" / "0011-identity-registry.sql"
MANIFEST_PATH = REPO_ROOT / "migrations" / "manifest.json"

REGISTRY_TABLES = (
    "users",
    "user_credentials",
    "agents",
    "agent_credentials",
    "auth_contract_state",
)


@pytest.fixture(scope="module")
def template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def statements(template: str) -> str:
    """The template with its comment lines removed.

    Every assertion about what the migration *does* reads this rather than the
    raw text. The file explains at length what it deliberately does not do -- no
    foreign key to `app.notes`, why `CHECK (v <> '')` is not enough on its own --
    and a scan that read those sentences reported them as the very things they
    warn about. Two of these tests failed exactly that way before this existed.
    """
    return "\n".join(line for line in template.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entry(manifest: dict[str, Any]) -> dict[str, Any]:
    for item in manifest["migrations"]:
        if item["template"].endswith("0011-identity-registry.sql"):
            return item
    pytest.fail("migration 0011 is not in the manifest")


# ---------------------------------------------------------------------------
# The registry exists, and is created rather than extended (D218)
# ---------------------------------------------------------------------------


def test_every_registry_table_is_created_from_nothing(template: str) -> None:
    """`CREATE TABLE`, not `ALTER TABLE ... ADD COLUMN`.

    The runbook's shape was nullable-add -> backfill -> validate -> NOT NULL over
    "inherited rows". There are none: `app_private` held `project_identity`, the
    ledger and the hook, and nothing else. A backfill over zero rows passes for a
    reason that is not correctness.
    """
    for table in REGISTRY_TABLES:
        assert re.search(rf"CREATE TABLE app_private\.{table}\b", template), table

    assert "ALTER TABLE" not in template, (
        "0011 alters nothing. Every column is NOT NULL from creation, which is only "
        "available because the tables are new"
    )


def test_no_column_is_added_nullable_and_backfilled(template: str) -> None:
    for forbidden in ("ADD COLUMN", "SET NOT NULL", "UPDATE app_private.", "VALIDATE CONSTRAINT"):
        assert forbidden not in template, (
            f"0011 contains {forbidden!r}; it creates, it does not migrate"
        )


def test_no_foreign_key_reaches_the_owner_column(statements: str) -> None:
    """`app.notes.owner_id` holds a claim value: trusted, not authenticated (ADR 0029).

    A foreign key would silently redefine it as a reference to `users`, and every
    row written before this migration would have to be deleted or invented.

    Reads `statements`, not `template`: the file explains this decision in prose,
    and the first version of this assertion matched its own explanation.
    """
    # The construct, not the substring. `app.notes` appears in this file three
    # times -- twice in `--` comments and once inside a COMMENT ON string literal
    # -- and the first two versions of this assertion matched the file's own
    # explanation of the decision. What "no foreign key" means is this:
    assert not re.search(r"REFERENCES\s+app\.", statements), (
        "0011 references a table in the `app` schema. `app.notes.owner_id` holds a claim "
        "value, and a foreign key would redefine it as a reference to the registry"
    )
    assert "owner_id" in statements, "the agents table's own owner_id should be here"


def test_the_agents_owner_is_a_real_foreign_key(template: str) -> None:
    """The distinction the test above depends on: this one IS a reference."""
    assert re.search(
        r"owner_id\s+uuid\s+NOT NULL REFERENCES app_private\.users \(id\)", template
    ), "an agent with no accountable owner is an authority nobody answers for"


# ---------------------------------------------------------------------------
# The NULL clause, which a measurement put there
# ---------------------------------------------------------------------------


def test_the_scope_check_cannot_return_null(template: str) -> None:
    """A CHECK constraint PASSES when its expression is NULL.

    Measured: the first draft of `is_scope_set` was
    `SELECT a = ARRAY(SELECT DISTINCT unnest(a) ORDER BY 1)`, and a real cluster
    accepted `ARRAY['a', NULL]` -- array comparison with a NULL element is NULL,
    and NULL is not false. Both clauses below are that finding.
    """
    body = template[template.index("CREATE FUNCTION app_private.is_scope_set") :]
    body = body[: body.index("COMMENT ON FUNCTION")]

    assert "coalesce(" in body, (
        "is_scope_set must not be able to return NULL; a NULL-returning shape admits "
        "exactly the rows it exists to refuse"
    )
    assert "array_position(a, NULL) IS NULL" in body, (
        "a NULL element must be refused explicitly. Without it the comparison below is "
        "unknown rather than false"
    )


def test_the_scope_check_is_immutable_and_pins_its_search_path(template: str) -> None:
    body = template[template.index("CREATE FUNCTION app_private.is_scope_set") :]
    body = body[: body.index("$fn$;")]
    assert "IMMUTABLE" in body, "a CHECK constraint cannot call a volatile function"
    assert "STRICT" in body
    assert "SET search_path = pg_catalog, pg_temp" in body


def test_every_text_column_with_an_emptiness_check_is_also_not_null(statements: str) -> None:
    """`CHECK (v <> '')` passes for NULL, measured on the locked image.

    So the emptiness check and `NOT NULL` are one guard written twice, and either
    alone admits a row nobody meant to allow. D218's "NOT NULL from creation" is
    doing more work than it looks.
    """
    for line in statements.splitlines():
        if "<> ''" in line and "CHECK" in line:
            assert "NOT NULL" in line, (
                f"an emptiness CHECK with no NOT NULL beside it: {line.strip()}"
            )


def test_both_scope_columns_are_checked_for_shape_and_for_emptiness(template: str) -> None:
    """Two constraints, because one does not imply the other.

    `is_scope_set(ARRAY[]::text[])` is true -- an empty array is trivially sorted
    and deduplicated -- so non-emptiness is its own line. Measured, not reasoned.
    """
    assert template.count("CHECK (app_private.is_scope_set(") == 3, (
        "users.scopes, agents.scopes and auth_contract_state.required_claims"
    )
    assert template.count("CHECK (array_length(") == 3


# ---------------------------------------------------------------------------
# The claim contract, tied to its one authority
# ---------------------------------------------------------------------------


def test_the_seeded_claim_set_is_the_module_s(template: str) -> None:
    """`jwt_claims` is the authority for the shape (ADR 0078); this is a copy.

    A copy tied by a test rather than by a placeholder: the claim list is not a
    per-project value, so putting it in the deployed document would be putting it
    where it does not belong. What makes the copy safe is that this comparison
    fails the moment the two disagree.
    """
    seeded = re.search(
        r"INSERT INTO app_private\.auth_contract_state \(required_claims\)"
        r" VALUES \(\s*ARRAY\[(.*?)\]::text\[\]",
        template,
        re.DOTALL,
    )
    assert seeded, "the contract row's seed could not be found"
    names = {item.strip().strip("'") for item in seeded.group(1).split(",")}

    assert names == set(jwt_claims.REQUIRED_CLAIMS), (
        "the migration seeds a claim set the module does not declare. jwt_claims is the "
        "one authority for the shape and this row is derived from it"
    )


def test_the_seeded_claim_set_is_sorted(template: str) -> None:
    """Because `is_scope_set` requires it -- the same constraint, applied to itself.

    The module's tuple is in *wire order*, which is what an issuer writes. This
    is the set, and the database's own shape rule is what makes it sorted here.
    """
    seeded = re.search(r"VALUES \(\s*ARRAY\[(.*?)\]::text\[\]", template, re.DOTALL)
    assert seeded
    names = [item.strip().strip("'") for item in seeded.group(1).split(",")]
    assert names == sorted(names), "the seed must satisfy the constraint it is written under"
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Privilege surface
# ---------------------------------------------------------------------------


def test_the_auth_service_gets_schema_usage_and_no_table_grant(template: str) -> None:
    """D228: 0011 creates tables and functions and grants USAGE. Nothing else.

    Measured on the applied cluster: `has_table_privilege(auth_service,
    'app_private.users', 'SELECT')` is false, and so is INSERT. The service
    reaches this data through definer functions that arrive with the code calling
    them -- a grant issued now would be a grant nobody can audit.
    """
    assert "GRANT USAGE ON SCHEMA app_private TO {{auth_service}};" in template
    for forbidden in ("GRANT SELECT", "GRANT INSERT", "GRANT UPDATE", "GRANT DELETE"):
        assert forbidden not in template, f"0011 issues {forbidden}"


def test_public_is_revoked_from_tables_and_functions(template: str) -> None:
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA app_private FROM PUBLIC;" in template
    assert "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app_private FROM PUBLIC;" in template


def test_no_function_is_created_in_the_api_schema(template: str) -> None:
    """The registry is private. Measured on the cluster: `api` gained none."""
    assert not re.search(r"CREATE (OR REPLACE )?FUNCTION api\.", template)
    assert not re.search(r"CREATE (TABLE|VIEW) api\.", template)


def test_the_migration_is_fix_forward_only(template: str) -> None:
    assert "AP900: released platform migrations are fix-forward only" in template


# ---------------------------------------------------------------------------
# The manifest agrees with the template
# ---------------------------------------------------------------------------


def test_the_manifest_declares_exactly_the_placeholders_used(
    entry: dict[str, Any], template: str
) -> None:
    """Both directions, which is the manifest schema's own rule.

    A declared non-use reads as evidence that a value still reaches the
    migration, which is why it is an error rather than a tidiness question.
    """
    used = set(re.findall(r"\{\{([a-z_]+)\}\}", template))
    assert set(entry["placeholders"]) == used, (
        f"declared {sorted(entry['placeholders'])}, used {sorted(used)}"
    )


def test_the_auth_service_placeholder_reads_the_derived_role(manifest: dict[str, Any]) -> None:
    placeholder = manifest["placeholders"]["auth_service"]
    assert placeholder["type"] == "identifier"
    assert placeholder["source"] == "database.roles.auth_service"


def test_0011_is_the_eleventh_and_the_lock_carries_it(entry: dict[str, Any]) -> None:
    """Released migrations are immutable and the numbering is a filesystem fact.

    D217: the runbook numbers Session 6's migrations 0009-0011, which would have
    collided with three released files on the first `dbmate up`.
    """
    lock = json.loads((REPO_ROOT / "migrations" / "released.lock.json").read_text(encoding="utf-8"))
    versions = [item["version"] for item in lock["migrations"]]
    assert entry["version"] in versions, "0011 is not in the released lock; run freeze-lock"
    assert versions == sorted(versions), "the lock is out of order"

    # Its POSITION, not the total. Run 8 appended 0012 (D261), and a test pinned
    # to the count would go red every time a migration is added -- which is the
    # one event the lock exists to record. What must not change is that 0011 is
    # the eleventh; what may is how many come after it.
    assert versions.index(entry["version"]) == 10
    assert len(versions) >= 11
