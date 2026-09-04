"""Project manifest schema and semantic validation (runbook §3.3-§3.6)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, config, naming

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
    """Both fixtures are at the NEWEST version (ADR 0183), so the shipped
    manifests exercise the shape the compiler reads rather than the one the
    host still runs -- D927's lesson, applied to this document."""
    document = config.load_project_manifest(path)
    assert document["schema_version"] == max(config.SUPPORTED_PROJECT_SCHEMA_VERSIONS)


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


def downgrade_to_two(document: dict[str, Any]) -> dict[str, Any]:
    """The same manifest at schema version 2 (ADR 0186): the lifecycle out,
    which is what a version 2 manifest says and means permanent."""
    document = copy.deepcopy(document)
    document["schema_version"] = 2
    document["project"].pop("lifecycle", None)
    return document


def downgrade(document: dict[str, Any]) -> dict[str, Any]:
    """The same manifest at schema version 1 (ADR 0183): the lifecycle out,
    the profile out, the two fields it replaced back in with the values the
    fixture carried for fifteen sessions. What the host's manifests still look
    like."""
    document = downgrade_to_two(document)
    document["schema_version"] = 1
    document["mcp"].pop("profile", None)
    document["mcp"]["max_result_rows"] = 100
    document["mcp"]["max_response_bytes"] = 262144
    return document


def set_at(document: dict[str, Any], pointer: tuple[str, ...], value: Any) -> None:
    node = document
    for key in pointer[:-1]:
        node = node.setdefault(key, {})
    node[pointer[-1]] = value


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        (("database", "max_client_connections"), 0),
        (("database", "max_client_connections"), 10001),
        (("database", "pool_size"), 0),
        (("api", "max_rows"), 10001),
        (("mcp", "profile", "query_resource", "max_rows"), 1001),
        (("mcp", "profile", "query_resource", "max_response_bytes"), 1023),
        (("mcp", "profile", "query_resource", "max_response_bytes"), 1048577),
        (("mcp", "profile", "query_resource", "max_concurrent_calls"), 33),
        (("mcp", "profile", "query_resource", "timeout_ms"), 99),
        (("mcp", "profile", "create_note", "max_affected_rows"), 101),
        (("storage", "upload_url_ttl_seconds"), 59),
        (("storage", "download_url_ttl_seconds"), 3601),
        (("storage", "max_upload_bytes"), 5368709121),
        (("backup", "retain_full"), 13),
    ],
)
def test_numeric_bounds_are_enforced(
    tmp_path: Path, base: dict[str, Any], pointer: tuple[str, ...], value: int
) -> None:
    set_at(base, pointer, value)
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        (("mcp", "max_result_rows"), 1001),
        (("mcp", "max_response_bytes"), 1023),
        (("mcp", "max_response_bytes"), 10485761),
    ],
)
def test_the_version_one_bounds_are_still_enforced_at_version_one(
    tmp_path: Path, base: dict[str, Any], pointer: tuple[str, ...], value: int
) -> None:
    """The two fields version 2 replaced (ADR 0183) are still bounded on the
    version 1 manifest the host runs. Asserted on a DOWNGRADED fixture: on the
    version 2 base these keys are refused as forbidden, which is a refusal for
    the wrong reason (D374)."""
    document = downgrade(base)
    assert check(tmp_path, copy.deepcopy(document)), "the control: the downgrade itself loads"
    set_at(document, pointer, value)
    with pytest.raises(config.ManifestError):
        check(tmp_path, document)


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
    """The CORS origin moves with the domain, and that coupling is the point.

    Session 5 requires the project's own HTTPS origin in
    `api.rest.allowed_cors_origins`, so changing the domain and not the origin
    now fails validation. That is the rule working: an allowlist that names the
    old domain is an allowlist that disables the documentation page and reports
    it as a browser error rather than as a manifest one.
    """
    base["project"]["domain"] = "xn--bcher-kva.example.test"
    base["api"]["rest"]["allowed_cors_origins"] = ["https://xn--bcher-kva.example.test"]
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
# Session 5: the REST service and its two derived prefixes
# ---------------------------------------------------------------------------


def test_rest_defaults_match_the_schema() -> None:
    """`default` annotates; it does not populate. Same rule as the budget.

    `config.API_REST_DEFAULTS` is what actually decides the value of an omitted
    key, so a schema whose defaults drifted from it would document one number
    and apply another.
    """
    schema = config.load_schema("project.schema.json")
    properties = schema["$defs"]["restService"]["properties"]
    from_schema = {key: value["default"] for key, value in properties.items() if "default" in value}
    assert from_schema == {
        key: value for key, value in config.API_REST_DEFAULTS.items() if key in from_schema
    }
    assert set(config.API_REST_DEFAULTS) <= set(properties)


def test_a_manifest_without_a_rest_section_is_valid(tmp_path: Path, base: dict[str, Any]) -> None:
    """The whole section is optional, and that is a decision rather than slack.

    Every project manifest written before Session 5 has no `api.rest`, including
    the two on the deployment host that are gitignored operator inputs. Making
    the section required would fail the next render on a host nobody had touched,
    and the honest render for a project that declares no REST service is one that
    publishes no REST route.
    """
    del base["api"]["rest"]
    assert "rest" not in check(tmp_path, base)["api"]


def test_a_disabled_rest_section_still_has_its_numbers_checked(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """Otherwise the manifest fails on the day somebody flips one boolean."""
    base["api"]["rest"]["enabled"] = False
    base["api"]["rest"]["allowed_cors_origins"] = []
    base["api"]["rest"]["request_body_memory_bytes"] = 4096
    with pytest.raises(config.ManifestError, match="request_body_memory_bytes"):
        check(tmp_path, base)


def test_the_body_limits_must_be_equal(tmp_path: Path, base: dict[str, Any]) -> None:
    """A memory limit below the accepted size is how a body reaches proxy disk."""
    base["api"]["rest"]["request_body_memory_bytes"] = 65536
    with pytest.raises(config.ManifestError, match="request_body_memory_bytes"):
        check(tmp_path, base)


def test_the_idle_timeout_must_be_below_the_lifetime(tmp_path: Path, base: dict[str, Any]) -> None:
    """At or above the lifetime it never fires, and reads as configured."""
    base["api"]["rest"]["pool_max_idle_seconds"] = 1800
    base["api"]["rest"]["pool_max_lifetime_seconds"] = 1800
    with pytest.raises(config.ManifestError, match="pool_max_idle_seconds"):
        check(tmp_path, base)


def test_the_connection_budget_must_fit(tmp_path: Path, base: dict[str, Any]) -> None:
    """The pooler's pool, the API's pool, its reservations and the admin reserve.

    The connection that cannot be opened when this is wrong is the pooler's or
    the migration's, and neither reports the reason as a capacity problem.
    """
    base["api"]["rest"]["pool_size"] = 30
    base["database"]["pool_size"] = 20
    base["database"]["max_connections"] = 50
    with pytest.raises(config.ManifestError, match="connection budget does not fit"):
        check(tmp_path, base)


def test_the_shipped_fixture_fits_its_own_budget() -> None:
    """Guard the guard: a rule nothing satisfies is a rule nobody has tested."""
    document = config.load_project_manifest(REPO_ROOT / "project.example.yaml")
    rest = document["api"]["rest"]
    committed = (
        config.postgrest_connection_budget(rest)
        + document["database"]["pool_size"]
        + config.ADMINISTRATION_RESERVED_CONNECTIONS
    )
    assert committed < config.DATABASE_BUDGET_DEFAULTS["max_connections"]


def test_the_projects_own_origin_must_be_allowed(tmp_path: Path, base: dict[str, Any]) -> None:
    base["api"]["rest"]["allowed_cors_origins"] = ["https://elsewhere.test"]
    with pytest.raises(config.ManifestError, match="allowed_cors_origins"):
        check(tmp_path, base)


@pytest.mark.parametrize(
    "origin",
    [
        pytest.param("null", id="null"),
        pytest.param("*", id="wildcard"),
        pytest.param("https://*.example.test", id="wildcard-host"),
        pytest.param("http://fixture-alpha-dev.test", id="not-https"),
        pytest.param("https://fixture-alpha-dev.test/", id="trailing-slash"),
        pytest.param("https://fixture-alpha-dev.test/app", id="path"),
        pytest.param("https://fixture-alpha-dev.test?a=1", id="query"),
        pytest.param("https://fixture-alpha-dev.test#f", id="fragment"),
        pytest.param("https://user@fixture-alpha-dev.test", id="userinfo"),
    ],
)
def test_a_cors_origin_that_is_not_an_exact_origin_is_refused(
    tmp_path: Path, base: dict[str, Any], origin: str
) -> None:
    """`null` is in this list first for a reason.

    It is the origin a sandboxed iframe and a `file://` document send, so an
    allowlist containing it admits anything that can arrange to be opaque -- and
    it is the one entry that looks like a placeholder rather than a permission.
    """
    base["api"]["rest"]["allowed_cors_origins"] = [
        "https://fixture-alpha-dev.test",
        origin,
    ]
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_a_duplicate_cors_origin_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    base["api"]["rest"]["allowed_cors_origins"] = [
        "https://fixture-alpha-dev.test",
        "https://fixture-alpha-dev.test",
    ]
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


@pytest.mark.parametrize(
    "duration",
    [
        pytest.param("0", id="bare-zero"),
        pytest.param("0s", id="zero-seconds"),
        pytest.param("5000", id="unitless"),
        pytest.param("5 s", id="space"),
        pytest.param("1m", id="minutes"),
        pytest.param("1s500ms", id="compound"),
        pytest.param("90s", id="above-the-ceiling"),
        pytest.param("50ms", id="below-the-floor"),
    ],
)
def test_a_statement_timeout_outside_the_grammar_is_refused(
    tmp_path: Path, base: dict[str, Any], duration: str
) -> None:
    """`0` is the entry that matters: PostgreSQL reads it as *disabled*.

    A grammar that admitted a bare integer or a zero would let a manifest turn
    the timeout off while looking exactly like one that set it.
    """
    base["api"]["rest"]["statement_timeouts"]["authenticated"] = duration
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_a_statement_timeout_on_a_role_that_does_not_exist_is_refused(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """Checked against `naming.ROLE_SUFFIXES`, not against a list written here.

    A timeout set on a role nothing derives is applied to nothing and reports
    nothing, and it reads in the manifest exactly like one that works.

    **This replaces a weaker version of itself, and D151 authorised the
    replacement in advance.** Until Session 5 Run 7 the negative example was
    `api_documentation` -- the role the runbook names and the platform did not
    derive -- with the note that "it will be namable here on the day it does".
    That day is now, so the example moved to a name nothing will ever derive,
    and the assertion that the check is against the *derivation* rather than
    against an enumeration is the same one, made against an input that cannot
    quietly become valid.
    """
    from agentic_postgres import naming

    assert "api_documentation_v2" not in naming.ROLE_SUFFIXES
    base["api"]["rest"]["statement_timeouts"]["api_documentation_v2"] = "5s"
    with pytest.raises(config.ManifestError, match="does not derive"):
        check(tmp_path, base)


def test_the_documentation_role_became_namable_when_it_was_derived(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """The other half, and the reason the test above could be replaced.

    D151: "The day the documentation role exists, it becomes namable here with
    no schema change and no test change." Run 7 appended it to
    `naming.ROLE_SUFFIXES` and nothing else moved -- no manifest schema change,
    no second list beside the derivation. This asserts that, so the claim is
    measured rather than remembered.

    Goes red if the manifest check ever stops reading `ROLE_SUFFIXES` and starts
    reading an enumeration written next to it, because then adding the fifteenth
    role would need two edits and only one of them would be obvious.
    """
    from agentic_postgres import naming

    assert "api_documentation" in naming.ROLE_SUFFIXES
    base["api"]["rest"]["statement_timeouts"]["api_documentation"] = "5s"
    check(tmp_path, base)


def test_anonymous_access_is_a_frozen_enumeration(tmp_path: Path, base: dict[str, Any]) -> None:
    base["api"]["rest"]["anonymous_access"] = "read_public"
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_the_rest_prefix_and_the_docs_prefix_are_distinct(base: dict[str, Any]) -> None:
    """Both are derived, which is exactly why they are checked rather than assumed."""
    rest = f"{base['api']['public_base_path']}{config.REST_PATH_SUFFIX}"
    assert rest == "/api/rest"
    assert config.DOCS_REST_PATH == "/docs/rest"
    assert not config.paths_overlap(rest, config.DOCS_REST_PATH)
    assert not config.paths_overlap(rest, base["mcp"]["public_base_path"])


def test_the_published_routes_and_the_compared_prefixes_are_one_derivation() -> None:
    """ADR 0061. The bug this closes was two constants that never met.

    `naming` derived `routes.docs` as the `/docs` root while `config` compared
    `/docs/rest`, and nothing put the two in the same expression -- so the
    document every consumer reads a route from pointed one segment above the
    only path Run 6 measured, and no test could see it. `bin/docs.sh check`
    would have reported 404 rather than 401, during Run 9's window.

    Goes red if: either constant is restated as a literal in `config` rather
    than read from `naming`; or a route is derived from something other than
    these paths, which is the direction that would let them drift apart again
    while both files still look right on their own.

    Asserted through the derived *URL*, not just the constants, because two
    constants agreeing is not the property -- the property is that the URL a
    consumer requests is built from the path the validator compared.
    """
    assert config.DOCS_REST_PATH is naming.DOCS_PAGE_PATH
    assert config.REST_PATH_SUFFIX is naming.REST_PATH_SUFFIX

    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    assert identity.route_docs.endswith(config.DOCS_REST_PATH)
    assert identity.route_rest.endswith(config.REST_PATH_SUFFIX)
    assert identity.route_rest_path == f"/api{config.REST_PATH_SUFFIX}"

    # The root stays reserved and stays unpublished. A route naming it would be
    # a status attached to something this session serves nothing at.
    assert naming.DOCS_ROOT_PATH in config.RESERVED_BASE_PATHS
    assert not identity.route_docs.endswith(naming.DOCS_ROOT_PATH)


def test_a_base_path_that_would_swallow_the_docs_prefix_is_refused(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """`/docs` is reserved, so this is already refused -- and is asserted anyway.

    The reserved list is a tuple somebody can edit. This states the consequence
    of editing it: the documentation route and a project route would answer on
    the same tree, and the edge would serve whichever router matched first.
    """
    base["mcp"]["public_base_path"] = "/docs/rest"
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_the_mcp_prefix_may_not_swallow_the_rest_prefix(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """The pair a manifest can actually produce, and the one nothing else caught.

    `api: /api` and `mcp: /api/rest` do not overlap under the existing check --
    which compares the two *base* paths -- but the derived REST prefix is exactly
    `/api/rest`, so the two published routes would be the same tree.
    """
    base["api"]["public_base_path"] = "/alpha"
    base["mcp"]["public_base_path"] = "/alpha/rest"
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


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
    """Both versions (ADR 0183): the one field at version 1, and every profiled
    `max_rows` at version 2. The relation survived the bump because at version
    2 the lock compiler READS the value, which makes it worth bounding."""
    document = downgrade(base)
    document["mcp"]["max_result_rows"] = 600
    document["api"]["max_rows"] = 500
    with pytest.raises(config.ManifestError, match="max_result_rows"):
        check(tmp_path, document)

    base["mcp"]["profile"]["query_resource"]["max_rows"] = 600
    base["api"]["max_rows"] = 500
    with pytest.raises(config.ManifestError, match=r"mcp\.profile\.query_resource\.max_rows"):
        check(tmp_path, base)


# ---------------------------------------------------------------------------
# Schema version 2: the profile replaces two fields nothing read (ADR 0183)
# ---------------------------------------------------------------------------


def test_version_two_requires_a_profile_and_forbids_the_two_inert_fields(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """A field is forbidden below the version that introduces it and required
    at or above it (ADR 0177's rule, applied to this document), and the two
    replaced fields are the mirror image. Both fixtures are version 3 since
    ADR 0186, so the version 2 arms run on a downgraded copy -- with the
    downgrade itself checked first, or every refusal below could be the
    downgrade's -- and the version 1 arms on a further one."""
    two = downgrade_to_two(base)
    assert check(tmp_path, copy.deepcopy(two))["schema_version"] == 2

    without = copy.deepcopy(two)
    del without["mcp"]["profile"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, without)

    for field, value in (("max_result_rows", 100), ("max_response_bytes", 262144)):
        carrying = copy.deepcopy(two)
        carrying["mcp"][field] = value
        with pytest.raises(config.ManifestError):
            check(tmp_path, carrying)

    empty = copy.deepcopy(two)
    empty["mcp"]["profile"] = {}
    assert check(tmp_path, empty)["mcp"]["profile"] == {}, "narrowing nothing is a valid state"

    v1 = downgrade(base)
    assert check(tmp_path, copy.deepcopy(v1))["schema_version"] == 1
    v1["mcp"]["profile"] = {"query_resource": {"max_rows": 10}}
    with pytest.raises(config.ManifestError):
        check(tmp_path, v1)


# ---------------------------------------------------------------------------
# Version 3: the lifecycle (ADR 0186)
# ---------------------------------------------------------------------------


def test_version_three_requires_a_lifecycle_and_lower_versions_forbid_it(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """ADR 0177's rule a third time. And the reading below the version: a
    manifest that says nothing means permanent, which is what the two host
    manifests -- both version 1 -- have always been."""
    assert base["schema_version"] == 3
    assert check(tmp_path, copy.deepcopy(base))["project"]["lifecycle"] == {"kind": "permanent"}

    without = copy.deepcopy(base)
    del without["project"]["lifecycle"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, without)

    two = downgrade_to_two(base)
    assert check(tmp_path, copy.deepcopy(two))["schema_version"] == 2
    two["project"]["lifecycle"] = {"kind": "permanent"}
    with pytest.raises(config.ManifestError):
        check(tmp_path, two)

    assert config.project_lifecycle(downgrade_to_two(base)) == {"kind": config.LIFECYCLE_PERMANENT}
    assert config.project_lifecycle(downgrade(base)) == {"kind": config.LIFECYCLE_PERMANENT}
    assert config.project_lifecycle(base) == {"kind": config.LIFECYCLE_PERMANENT}


def test_an_ephemeral_project_carries_an_expiry_and_a_permanent_one_may_not(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """`expires_at` is required exactly when the kind is ephemeral: an
    ephemeral project with no end is a permanent one with a misleading label,
    and a permanent project with an end is the reverse."""
    ephemeral = copy.deepcopy(base)
    ephemeral["project"]["lifecycle"] = {"kind": "ephemeral"}
    with pytest.raises(config.ManifestError):
        check(tmp_path, ephemeral)

    ephemeral["project"]["lifecycle"]["expires_at"] = "2999-01-01T00:00:00Z"
    loaded = check(tmp_path, copy.deepcopy(ephemeral))
    assert config.project_lifecycle(loaded) == {
        "kind": "ephemeral",
        "expires_at": "2999-01-01T00:00:00Z",
    }

    permanent = copy.deepcopy(base)
    permanent["project"]["lifecycle"] = {"kind": "permanent", "expires_at": "2999-01-01T00:00:00Z"}
    with pytest.raises(config.ManifestError):
        check(tmp_path, permanent)

    # The shape is `observed_at`'s: UTC, second precision, `Z`. An offset form
    # names the same instant and is refused, so one instant has one spelling.
    offset = copy.deepcopy(ephemeral)
    offset["project"]["lifecycle"]["expires_at"] = "2999-01-01T00:00:00+00:00"
    with pytest.raises(config.ManifestError):
        check(tmp_path, offset)


def test_a_project_born_expired_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """The render is the last moment a human is looking, and a typo in a date
    is invisible after it. Equal is expired: an `expires_at` of now expires now."""
    from datetime import UTC, datetime

    born_expired = copy.deepcopy(base)
    born_expired["project"]["lifecycle"] = {
        "kind": "ephemeral",
        "expires_at": "2000-01-01T00:00:00Z",
    }
    with pytest.raises(config.ManifestError, match="born expired"):
        check(tmp_path, born_expired)

    at_noon = copy.deepcopy(base)
    at_noon["project"]["lifecycle"] = {"kind": "ephemeral", "expires_at": "2026-09-04T12:00:00Z"}
    noon = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(config.ManifestError, match="born expired"):
        config.validate_project_semantics(at_noon, now=noon)
    config.validate_project_semantics(at_noon, now=noon.replace(minute=0, second=0, hour=11))


def test_a_profile_entry_is_typed_and_non_empty(tmp_path: Path, base: dict[str, Any]) -> None:
    """The schema's half of the refusals: an unknown field, a wrong type, a
    tool name outside the identifier grammar, an empty entry. The compiler's
    half -- widening, wrong kind, unknown tool -- needs the compiled contract
    and lives in test_capability_profile.py."""
    for entry in (
        {"columns": ["id"]},
        {"max_rows": "100"},
        {"supports_dry_run": "false"},
        {},
    ):
        document = copy.deepcopy(base)
        document["mcp"]["profile"] = {"query_resource": entry}
        with pytest.raises(config.ManifestError):
            check(tmp_path, document)

    document = copy.deepcopy(base)
    document["mcp"]["profile"] = {"Delete-Everything": {"timeout_ms": 100}}
    with pytest.raises(config.ManifestError):
        check(tmp_path, document)


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


# A public pooler is no longer a supported profile (ADR 0040). Through Session 3
# these tests proved that `pooled_public: true` was accepted with a validated
# CIDR allowlist and refused without one. Their replacements are strictly
# stronger: every input the old tests *accepted* is now refused, and nothing the
# old tests refused is now accepted. That direction is the requirement ADR 0017
# sets for replacing a passing test, and it is worth stating rather than
# assuming, because the easy version of this change would have been to delete
# the four tests that no longer applied.


def test_a_public_pool_is_refused_outright(tmp_path: Path, base: dict[str, Any]) -> None:
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = []
    with pytest.raises(config.ManifestError, match="not a supported profile"):
        check(tmp_path, base)


@pytest.mark.parametrize(
    "cidrs",
    [
        pytest.param(["203.0.113.0/24"], id="one-specific-network"),
        pytest.param(["203.0.113.0/24", "2001:db8::/32"], id="two-specific-networks"),
        pytest.param(["10.0.0.0/8"], id="private-network"),
    ],
)
def test_no_allowlist_makes_a_public_pool_supported(
    tmp_path: Path, base: dict[str, Any], cidrs: list[str]
) -> None:
    """The case the old suite accepted, and the reason this replacement is stricter.

    `test_public_pool_accepts_a_specific_network` passed a well-formed allowlist
    and asserted the manifest loaded. A narrow allowlist is still a public bind,
    and ADR 0040 draws the boundary at loopback rather than at audience.
    """
    base["database"]["pooled_public"] = True
    base["database"]["pooled_public_cidrs"] = cidrs
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_the_refusal_names_the_supported_path(tmp_path: Path, base: dict[str, Any]) -> None:
    """An operator who asked for this needs to be told what to do instead.

    A refusal that only says no leaves them to guess, and the likeliest guess is
    to publish the port by hand outside the runtime override, which is the one
    path nothing here can prevent.
    """
    base["database"]["pooled_public"] = True
    with pytest.raises(config.ManifestError) as raised:
        check(tmp_path, base)
    assert "ADR 0040" in str(raised.value)
    assert "connect.sh" in str(raised.value)


def test_cidrs_must_be_empty_even_when_the_pool_is_private(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    base["database"]["pooled_public"] = False
    base["database"]["pooled_public_cidrs"] = ["203.0.113.0/24"]
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


# ---------------------------------------------------------------------------
# Pool settings (Session 4 Run 2)
# ---------------------------------------------------------------------------


def test_pool_defaults_match_the_schema() -> None:
    """The duplication in config.POOL_DEFAULTS cannot drift silently."""
    schema = config.load_schema("project.schema.json")
    properties = schema["properties"]["database"]["properties"]
    for key, value in config.POOL_DEFAULTS.items():
        assert properties[key]["default"] == value, key


def test_prepared_statement_tracking_cannot_be_disabled(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """0 is the value that breaks the clients, so it is out of bounds.

    Measured against the locked image in Run 1: at 0, a named prepared statement
    is unusable the moment transaction pooling moves the client to a different
    backend. This is the setting a failing client test must never be fixed by
    lowering, so it cannot be lowered that far.
    """
    base["database"]["max_prepared_statements"] = 0
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_the_queue_timeout_must_be_shorter_than_the_idle_transaction_timeout(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    base["database"]["query_wait_timeout_seconds"] = 60
    base["database"]["idle_transaction_timeout_seconds"] = 60
    with pytest.raises(config.ManifestError, match="must be less than"):
        check(tmp_path, base)


def test_the_default_pool_settings_are_consistent(tmp_path: Path, base: dict[str, Any]) -> None:
    """The defaults must satisfy the relation, or every manifest fails closed."""
    for key in list(config.POOL_DEFAULTS):
        base["database"].pop(key, None)
    assert check(tmp_path, base)["database"].get("pooled_public") is False


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


# ---------------------------------------------------------------------------
# Session 7: the storage service's bounds and the fourth connection claimant
# ---------------------------------------------------------------------------


def test_storage_defaults_match_the_schema() -> None:
    """The duplication in `config.STORAGE_DEFAULTS` cannot drift silently.

    `default` in JSON Schema annotates; it does not populate. A validator
    accepts a manifest naming none of these and hands it back unchanged, so
    `STORAGE_DEFAULTS` is what actually decides the value -- and the renderer
    resolves the document's storage block through it, so a drift here is a bound
    the runtime enforces and the manifest never approved.

    `enabled` is excluded: it is `required` in the schema, so there is no
    default to compare against, and the mapping's `False` is what a caller that
    omits the whole section gets.

    **`account_id` is excluded too, and the exclusion IS the decision rather
    than an exemption from it** (ADR 0106, Session 7 Run 5). It deliberately has
    no schema default, because a default account id would be a well-formed value
    that authenticates to nothing -- ADR 0055's and D333's shape, where a
    generated stand-in for an operator-supplied value was entirely plausible and
    useless. `STORAGE_DEFAULTS` carries `None` so that
    `{**STORAGE_DEFAULTS, **manifest}` has the key at all; the requirement is
    enforced by `config._validate_storage`, whose message can name the operator
    guide as a schema failure cannot, and `test_storage_defaults_carry_no_account_id`
    asserts the `None`.

    The exclusions are a named set, and each one is asserted to have no schema
    default rather than merely skipped -- otherwise this test would go quiet in
    exactly the case where somebody added the default it exists to forbid.
    """
    schema = config.load_schema("project.schema.json")
    properties = schema["properties"]["storage"]["properties"]
    without_defaults = {"enabled", "account_id"}
    compared = 0
    for key, value in config.STORAGE_DEFAULTS.items():
        if key in without_defaults:
            assert "default" not in properties[key], (
                f"{key} is skipped here because it has no schema default, and it now "
                "has one -- so either this exclusion or the schema is wrong"
            )
            continue
        assert properties[key]["default"] == value, key
        compared += 1
    assert compared == len(config.STORAGE_DEFAULTS) - len(without_defaults), (
        "the loop compared fewer keys than the mapping holds; a `continue` is "
        "swallowing something it was not written for"
    )


def test_the_origin_patterns_agree() -> None:
    """One grammar for an HTTPS origin, stated in two schemas that share no $defs.

    `project.schema.json` bounds what an operator may write and
    `outputs.schema.json` bounds what the render publishes; a document cannot
    $ref across files here, so the pattern is written twice. This is what makes
    the second copy safe -- and it is a real risk rather than a theoretical one,
    because the whole value of the pattern is the four things it refuses
    (a wildcard, plain http, a path, and the literal `null`) and a copy that
    relaxed any of them would still look like an allowlist.
    """
    project = config.load_schema("project.schema.json")
    outputs = config.load_schema("outputs.schema.json")

    rest = project["$defs"]["restService"]["properties"]
    storage = project["properties"]["storage"]["properties"]
    published = outputs["$defs"]["httpsOrigin"]

    patterns = {
        "api.rest.allowed_cors_origins": rest["allowed_cors_origins"]["items"]["pattern"],
        "storage.allowed_cors_origins": storage["allowed_cors_origins"]["items"]["pattern"],
        "outputs $defs/httpsOrigin": published["pattern"],
    }
    assert len(set(patterns.values())) == 1, f"the origin grammars have diverged: {patterns}"

    # And the grammar actually refuses what it is for. Asserted by matching,
    # not by reading the regex: a pattern test that only compares two strings
    # goes green when both copies are wrong.
    import re

    compiled = re.compile(next(iter(patterns.values())))
    for accepted in ("https://app.example.test", "https://app.example.test:8443"):
        assert compiled.match(accepted), accepted
    for refused in (
        "*",
        "https://*.example.test",
        "http://app.example.test",
        "null",
        "https://app.example.test/path",
        "https://user@app.example.test",
        "https://app.example.test?q=1",
        "https://app.example.test#f",
    ):
        assert not compiled.match(refused), refused


def test_the_connection_budget_charges_the_storage_service(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """ADR 0099's fourth claimant, refused when the sum does not fit.

    Paired with a control on the line below the refusal: the same manifest at a
    pool size that fits must pass. Without it this would not distinguish
    "charges storage" from "refuses every manifest".
    """
    base.setdefault("storage", {"enabled": False})
    base["storage"]["pool_size"] = 4
    check(tmp_path, base)  # control: the default division fits

    base["storage"]["pool_size"] = 40
    with pytest.raises(config.ManifestError, match=r"storage\.pool_size"):
        check(tmp_path, base)


def test_the_storage_budget_is_charged_even_when_storage_is_disabled(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """A division that moved when somebody toggled a flag would make the
    bootstrap plane's arithmetic depend on a flag it does not read.

    The same property D256 recorded for the REST service, which sat behind two
    early returns and ran only for an enabled one.
    """
    base["storage"] = {"enabled": False, "pool_size": 40}
    with pytest.raises(config.ManifestError, match=r"storage\.pool_size"):
        check(tmp_path, base)


def test_a_wildcard_or_http_storage_origin_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """The negative cases Run 1 owes, on the field that will render two policies.

    A control first: a well-formed HTTPS origin is accepted, so a passing test
    below cannot be a manifest that is refused for some unrelated reason.
    """
    base["storage"] = {
        "enabled": True,
        "bucket": "fixture-alpha-dev",
        "prefix": "objects/fixture-alpha-dev/",
        # Required once storage is enabled (ADR 0106). Present so that the
        # control below fails for the reason this test is about, rather than for
        # a missing account -- which is the whole job of a control.
        "account_id": "0123456789abcdef0123456789abcdef",
        "allowed_cors_origins": ["https://app.fixture-alpha-dev.test"],
    }
    check(tmp_path, base)

    for refused in (
        "*",
        "https://*.fixture-alpha-dev.test",
        "http://app.fixture-alpha-dev.test",
        "null",
        "https://app.fixture-alpha-dev.test/uploads",
    ):
        base["storage"]["allowed_cors_origins"] = [refused]
        with pytest.raises(config.ManifestError):
            check(tmp_path, base)


def test_a_disabled_storage_service_may_name_no_origin(
    tmp_path: Path, base: dict[str, Any]
) -> None:
    """An origin list on a surface that is not served is a policy nobody applies."""
    base["storage"] = {
        "enabled": False,
        "allowed_cors_origins": ["https://app.fixture-alpha-dev.test"],
    }
    with pytest.raises(config.ManifestError):
        check(tmp_path, base)


def test_a_storage_bound_outside_its_range_is_refused(tmp_path: Path, base: dict[str, Any]) -> None:
    """ADR 0007 keeps bounds in the schema; this is what proves they are enforced."""
    base.setdefault("storage", {"enabled": False})
    for field, value in (
        ("upload_url_ttl_seconds", 59),
        ("upload_url_ttl_seconds", 3601),
        ("download_url_ttl_seconds", 59),
        ("download_url_ttl_seconds", 3601),
        ("max_upload_bytes", 0),
        ("max_upload_bytes", 5368709121),
        ("pool_size", 0),
        ("pool_size", 65),
    ):
        candidate = {**base, "storage": {**base["storage"], field: value}}
        with pytest.raises(config.ManifestError):
            check(tmp_path, candidate)
