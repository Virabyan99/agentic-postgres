"""Project manifest schema and semantic validation (runbook §3.3-§3.6)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURES = (
    REPO_ROOT / "project.example.yaml",
    REPO_ROOT / "project.second.example.yaml",
)


@pytest.fixture
def base() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "project.example.yaml").read_text(encoding="utf-8"))


def check(tmp_path: Path, document: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return config.load_project_manifest(path)


# ---------------------------------------------------------------------------
# The shipped fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_example_manifest_is_valid(path: Path) -> None:
    document = config.load_project_manifest(path)
    assert document["schema_version"] == 1


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_example_manifest_carries_no_secret_material(path: Path) -> None:
    config.assert_no_sensitive_keys(config.load_manifest(path))


# ---------------------------------------------------------------------------
# Schema strictness
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_is_rejected(tmp_path: Path, base: dict[str, Any]) -> None:
    base["unexpected"] = True
    with pytest.raises(config.ManifestError, match="unexpected"):
        check(tmp_path, base)


def test_unknown_nested_key_is_rejected(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["surprise"] = 1
    with pytest.raises(config.ManifestError, match="surprise"):
        check(tmp_path, base)


def test_unsupported_schema_version_is_rejected(tmp_path: Path, base: dict[str, Any]) -> None:
    base["schema_version"] = 99
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("section", ["project", "database", "api", "mcp"])
def test_required_section_is_required(tmp_path: Path, base: dict[str, Any], section: str) -> None:
    del base[section]
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        (("database", "max_client_connections"), 0),
        (("database", "max_client_connections"), 10001),
        (("database", "pool_size"), 0),
        (("api", "max_rows"), 10001),
        (("mcp", "max_result_rows"), 1001),
        (("mcp", "max_response_bytes"), 1023),
        (("mcp", "max_response_bytes"), 10485761),
        (("storage", "upload_url_ttl_seconds"), 59),
        (("storage", "download_url_ttl_seconds"), 3601),
        (("storage", "max_upload_bytes"), 5368709121),
        (("backup", "retain_full"), 13),
    ],
)
def test_numeric_bounds_are_enforced(
    tmp_path: Path, base: dict[str, Any], pointer: tuple[str, str], value: int
) -> None:
    base[pointer[0]][pointer[1]] = value
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_bounds_are_declared_only_in_the_schema() -> None:
    """Plan decision E: the schema is the sole authority for numeric bounds."""
    rows = config.bounds_table()
    fields = {row["field"] for row in rows}
    assert "database.max_client_connections" in fields
    assert "mcp.max_response_bytes" in fields
    assert "backup.retain_full" in fields

    for row in rows:
        assert row["minimum"] is not None or row["maximum"] is not None
        assert row["description"], f"{row['field']} has no description to document"


# ---------------------------------------------------------------------------
# Slug, environment, domain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["ab", "A-bad", "-lead", "x" * 32, "has_underscore"])
def test_invalid_slug_is_rejected(tmp_path: Path, base: dict[str, Any], slug: str) -> None:
    base["project"]["slug"] = slug
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("environment", ["d", "Dev", "x" * 17, "1dev"])
def test_invalid_environment_is_rejected(
    tmp_path: Path, base: dict[str, Any], environment: str
) -> None:
    base["project"]["environment"] = environment
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize(
    "domain",
    [
        "https://example.test",
        "example.test:5432",
        "example.test/path",
        "*.example.test",
        "example.test.",
        "EXAMPLE.test",
        "192.0.2.1",
        "localhost",
        "-bad.example.test",
    ],
)
def test_invalid_domain_is_rejected(tmp_path: Path, base: dict[str, Any], domain: str) -> None:
    base["project"]["domain"] = domain
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_punycode_domain_is_accepted(tmp_path: Path, base: dict[str, Any]) -> None:
    base["project"]["domain"] = "xn--bcher-kva.example.test"
    assert check(tmp_path, base)["project"]["domain"] == "xn--bcher-kva.example.test"


# ---------------------------------------------------------------------------
# Route paths and overlap (plan decision B)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["api", "/", "/api/", "/api//v1", "/api/../admin", "/api/./v1", "/apî"],
)
def test_invalid_base_path_is_rejected(tmp_path: Path, base: dict[str, Any], path: str) -> None:
    base["api"]["public_base_path"] = path
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("reserved", ["/docs", "/health", "/metrics", "/.well-known"])
def test_reserved_route_collision_is_rejected(
    tmp_path: Path, base: dict[str, Any], reserved: str
) -> None:
    base["api"]["public_base_path"] = reserved
    with pytest.raises(config.ManifestError, match="reserved route"):
        check(tmp_path, base)


def test_route_below_a_reserved_prefix_is_rejected(tmp_path: Path, base: dict[str, Any]) -> None:
    base["api"]["public_base_path"] = "/docs/v1"
    with pytest.raises(config.ManifestError, match="reserved route"):
        check(tmp_path, base)


def test_api_and_mcp_trees_may_not_overlap(tmp_path: Path, base: dict[str, Any]) -> None:
    base["api"]["public_base_path"] = "/api"
    base["mcp"]["public_base_path"] = "/api/mcp"
    with pytest.raises(config.ManifestError, match="overlap ambiguously"):
        check(tmp_path, base)


def test_similar_but_distinct_prefixes_are_allowed(tmp_path: Path, base: dict[str, Any]) -> None:
    """`/api` and `/apiv2` do not overlap; a str.startswith check would say they do."""
    base["api"]["public_base_path"] = "/api"
    base["mcp"]["public_base_path"] = "/apiv2"
    assert check(tmp_path, base)["mcp"]["public_base_path"] == "/apiv2"


def test_paths_overlap_is_segment_wise() -> None:
    assert config.paths_overlap("/api", "/api/v1")
    assert config.paths_overlap("/api", "/api")
    assert not config.paths_overlap("/api", "/apiv2")
    assert not config.paths_overlap("/api", "/mcp")


def test_root_is_not_treated_as_a_reserved_prefix() -> None:
    """Root has no segments, so it prefixes everything.

    Including `/` in RESERVED_BASE_PATHS would therefore reject every possible
    base path. Root is rejected by an explicit equality check instead.
    """
    assert not config.paths_overlap("/api", "/")
    assert "/" not in config.RESERVED_BASE_PATHS


# ---------------------------------------------------------------------------
# Cross-field relations
# ---------------------------------------------------------------------------


def test_pool_size_may_not_exceed_max_client_connections(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    base["database"]["pool_size"] = 200
    base["database"]["max_client_connections"] = 100
    with pytest.raises(config.ManifestError, match="pool_size"):
        check(tmp_path, base)


def test_mcp_rows_may_not_exceed_api_rows(tmp_path: Path, base: dict[str, Any]) -> None:
    base["mcp"]["max_result_rows"] = 600
    base["api"]["max_rows"] = 500
    with pytest.raises(config.ManifestError, match="max_result_rows"):
        check(tmp_path, base)


# ---------------------------------------------------------------------------
# The Session 3 memory budget (D52, ADR 0007 for the bounds)
# ---------------------------------------------------------------------------


def test_budget_defaults_match_the_schema() -> None:
    """`default` in JSON Schema annotates; it does not populate.

    A validator accepts a manifest without these keys and hands it back
    unchanged, so `config.DATABASE_BUDGET_DEFAULTS` is what actually decides
    the value. This is the test that stops the two from drifting -- a schema
    default nothing reads is documentation that lies.
    """
    import json

    schema = json.loads((REPO_ROOT / "schemas" / "project.schema.json").read_text(encoding="utf-8"))
    properties = schema["properties"]["database"]["properties"]
    for key, value in config.DATABASE_BUDGET_DEFAULTS.items():
        assert properties[key]["default"] == value, key


def test_a_manifest_that_declares_no_budget_gets_the_defaults(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    document = check(tmp_path, base)
    budget = config.database_budget(document["database"])
    for key, value in config.DATABASE_BUDGET_DEFAULTS.items():
        assert budget[key] == value, key


def test_the_derived_total_excludes_work_mem(tmp_path: Path, base: dict[str, Any]) -> None:
    """Measured, not reasoned: `work_mem` is a per-sort ceiling, not a reservation.

    Charging `max_connections x work_mem` would add 200 MiB per cluster at the
    defaults, for memory two measured clusters never allocated. A guardrail that
    refuses configurations which fit is one that gets raised.
    """
    budget = config.database_budget(base["database"])
    assert budget["unreclaimable_mb"] == (
        budget["shared_buffers_mb"]
        + budget["maintenance_work_mem_mb"]
        + budget["max_connections"] * config.PER_BACKEND_ANON_MB
    )
    base["database"]["work_mem_mb"] = 64
    raised = config.database_budget(base["database"])
    assert raised["unreclaimable_mb"] == budget["unreclaimable_mb"]


def test_shm_size_below_shared_buffers_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """Docker's 64 MiB default /dev/shm is below the default shared_buffers."""
    base["database"]["shared_buffers_mb"] = 256
    base["database"]["shm_size_mb"] = 64
    with pytest.raises(config.ManifestError, match="shm_size_mb"):
        check(tmp_path, base)


def test_a_memory_limit_at_the_budget_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """The measured failure: a limit equal to the budget caps page cache too.

    Two clusters at 512 MiB pegged their limit with several hundred reclaim
    events and no OOM kill -- functional, permanently thrashing, and invisible
    to anything that only asks whether the container is running.
    """
    budget = config.database_budget(base["database"])
    base["database"]["memory_limit_mb"] = budget["unreclaimable_mb"]
    with pytest.raises(config.ManifestError, match="does not exceed the unreclaimable budget"):
        check(tmp_path, base)


def test_a_budget_over_the_host_guardrail_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["shared_buffers_mb"] = 1024
    base["database"]["maintenance_work_mem_mb"] = 512
    base["database"]["max_connections"] = 200
    base["database"]["memory_limit_mb"] = 4096
    base["database"]["shm_size_mb"] = 1024
    with pytest.raises(config.ManifestError, match="exceeds the per-host"):
        check(tmp_path, base)


def test_two_projects_at_the_defaults_fit_the_host(tmp_path: Path) -> None:
    """The claim D52 actually makes, checked rather than asserted in prose.

    Both shipped manifests, summed, against the declared guardrail. Measured
    consumption was lower still (~218 MiB per cluster against 292 charged), and
    the guardrail is conservative in the direction that costs a redeploy rather
    than an OOM kill on a host with no swap.
    """
    total = 0
    for path in FIXTURES:
        document = config.load_project_manifest(path)
        total += config.database_budget(document["database"])["unreclaimable_mb"]
    assert total <= config.HOST_MEMORY_GUARDRAIL_MB, (
        f"two projects at their declared budgets need {total} MiB, "
        f"over the {config.HOST_MEMORY_GUARDRAIL_MB} MiB guardrail"
    )


# ---------------------------------------------------------------------------
# Conditional rules
# ---------------------------------------------------------------------------


def test_public_pool_requires_a_cidr_allowlist(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = []
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("cidr", ["0.0.0.0/0", "::/0"])
def test_public_pool_rejects_a_default_route(
    tmp_path: Path, base: dict[str, Any], cidr: str
) -> None:
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = [cidr]
    with pytest.raises(config.ManifestError, match="default route"):
        check(tmp_path, base)


def test_public_pool_rejects_a_malformed_cidr(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = ["203.0.113.5/24"]  # host bits set
    with pytest.raises(config.ManifestError, match="invalid CIDR"):
        check(tmp_path, base)


def test_public_pool_accepts_a_specific_network(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = ["203.0.113.0/24", "2001:db8::/32"]
    assert len(check(tmp_path, base)["database"]["pooled_public_cidrs"]) == 2


def test_cidrs_must_be_empty_when_pool_is_private(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["pooled_public"] = False
    base["database"]["pooled_public_cidrs"] = ["203.0.113.0/24"]
    with pytest.raises(config.ManifestError, match="must be empty"):
        check(tmp_path, base)


def test_disabled_storage_must_not_declare_a_bucket(tmp_path: Path, base: dict[str, Any]) -> None:
    base["storage"] = {"enabled": False, "bucket": "leftover-bucket", "prefix": None}
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_disabled_backup_must_not_declare_a_stanza(tmp_path: Path, base: dict[str, Any]) -> None:
    base["backup"] = {"enabled": False, "stanza": "leftover", "repository_prefix": None}
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_disabled_features_validate_when_fields_are_absent(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    base["storage"] = {"enabled": False}
    base["backup"] = {"enabled": False}
    assert check(tmp_path, base)["storage"] == {"enabled": False}


# ---------------------------------------------------------------------------
# Identifier and prefix rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Fixture", "1bad", "has-hyphen", "a" * 64])
def test_invalid_database_name_is_rejected(tmp_path: Path, base: dict[str, Any], name: str) -> None:
    base["database"]["name"] = name
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("bucket", ["ab", "-lead", "trail-", "UPPER", "a" * 64])
def test_invalid_bucket_is_rejected(tmp_path: Path, base: dict[str, Any], bucket: str) -> None:
    base["storage"]["bucket"] = bucket
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("prefix", ["/absolute/", "no-trailing-slash", "../escape/", "a/../../b/"])
def test_invalid_storage_prefix_is_rejected(
    tmp_path: Path, base: dict[str, Any], prefix: str
) -> None:
    base["storage"]["prefix"] = prefix
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_prefix_with_a_control_character_is_rejected(tmp_path: Path, base: dict[str, Any]) -> None:
    base["storage"]["prefix"] = "objects/\x07bell/"
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize("stanza", ["has space", "has/slash", "-lead", "UPPER"])
def test_invalid_backup_stanza_is_rejected(
    tmp_path: Path, base: dict[str, Any], stanza: str
) -> None:
    base["backup"]["stanza"] = stanza
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


# ---------------------------------------------------------------------------
# Secret-key defense (plan decision F)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "secret",
        "token",
        "db_password",
        "aws_secret_access_key",
        "client_secret",
        "api_token",
        "refresh_token",
        "jwt_signing_key",
        "provider_credentials",
    ],
)
def test_sensitive_keys_are_rejected(key: str) -> None:
    assert config.is_sensitive_key(key), f"{key} should be treated as secret material"


@pytest.mark.parametrize(
    "key",
    [
        "password_secret_ref",
        "token_ttl_seconds",
        "token_use",
        "secret_ref",
        "tokenizer",
        "secretariat",
        "public_base_path",
        "max_upload_bytes",
    ],
)
def test_safe_keys_are_not_false_positives(key: str) -> None:
    assert not config.is_sensitive_key(key), f"{key} is not secret material"


def test_sensitive_key_is_rejected_at_depth(tmp_path: Path, base: dict[str, Any]) -> None:
    # Planting a secret-looking key is the entire point of this test.
    base["database"]["password"] = "hunter2"  # noqa: S105
    with pytest.raises(config.ManifestError, match="secret material"):
        check(tmp_path, base)


def test_sensitive_key_inside_a_list_is_rejected() -> None:
    document = {"items": [{"ok": 1}, {"api_token": "x"}]}
    with pytest.raises(config.ManifestError, match=r"items\[1\].api_token"):
        config.assert_no_sensitive_keys(document)


def test_allowlisted_key_survives_the_recursive_scan() -> None:
    config.assert_no_sensitive_keys({"database": {"password_secret_ref": None}})


def test_fixtures_are_not_mutated_by_validation(base: dict[str, Any]) -> None:
    """Validation must not rewrite its input; the renderer hashes the file."""
    before = copy.deepcopy(base)
    config.validate_project_semantics(base)
    assert base == before
