"""Contract tests for deterministic identity derivation (runbook §3.7, §3.8).

The fixture pair deliberately does *not* exercise truncation. The longest role
either fixture produces is 46 bytes, 17 under the PostgreSQL ceiling — they
exercise the §8 *collision* contract instead. Truncation is only reachable at
the top of the input space the schema permits, so this module builds synthetic
maximum-length and boundary inputs to reach it. See
``test_fixtures_do_not_reach_the_truncation_boundary``, which asserts that
distinction rather than leaving it as a comment.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import naming

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REPO_ROOT = Path(__file__).resolve().parents[2]

# Largest values the manifest schema permits:
#   slug        ^[a-z][a-z0-9-]{2,30}$   -> 31 characters
#   environment ^[a-z][a-z0-9-]{1,15}$   -> 16 characters
MAX_SLUG = "s" + "a" * 30
MAX_ENVIRONMENT = "e" + "b" * 15


def _slug_of_length(n: int) -> str:
    assert 3 <= n <= 31
    return "s" + "a" * (n - 1)


#: (slug, environment) pairs spanning both fixtures and the boundary region.
#: A role is ``5 + len(project_key) + len(suffix)`` bytes, and the longest
#: suffix is ``postgrest_authenticator`` (23), so a project key of 35 lands the
#: longest role on exactly 63 and 36 pushes it over.
CORPUS: tuple[tuple[str, str], ...] = (
    ("fixture-alpha", "dev"),
    ("fixture-alpine", "dev"),
    (_slug_of_length(30), "dev"),  # project_key 34 -> longest role 62
    (_slug_of_length(31), "dev"),  # project_key 35 -> longest role 63 exactly
    (_slug_of_length(31), "dev1"),  # project_key 36 -> truncation fires
    (MAX_SLUG, MAX_ENVIRONMENT),  # project_key 48 -> untruncated role 76
)


# ---------------------------------------------------------------------------
# Property 1 — per-role independent derivation, nothing past 63 bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("slug", "environment"), CORPUS)
def test_every_role_stays_within_63_bytes(slug: str, environment: str) -> None:
    key_sql = naming.sql_key(naming.project_key(slug, environment))
    roles = naming.database_roles(key_sql)

    assert set(roles) == set(naming.ROLE_SUFFIXES)
    for suffix, name in roles.items():
        assert len(name.encode("utf-8")) <= naming.POSTGRES_IDENTIFIER_MAX, (
            f"role {suffix} is {len(name.encode())} bytes: {name}"
        )


@pytest.mark.parametrize(("slug", "environment"), CORPUS)
def test_roles_are_pairwise_distinct(slug: str, environment: str) -> None:
    roles = naming.database_roles(naming.sql_key(naming.project_key(slug, environment)))
    assert len(set(roles.values())) == len(naming.ROLE_SUFFIXES)


def test_roles_are_derived_independently_not_from_a_shared_prefix() -> None:
    """Rule 9: each complete role name is derived and truncated on its own.

    A shared truncated prefix with per-role suffixes appended would give every
    role the *same* fingerprint, and would let a long suffix push the total
    past 63 bytes. Distinct fingerprints prove each full name was hashed.
    """
    key_sql = naming.sql_key(naming.project_key(MAX_SLUG, MAX_ENVIRONMENT))
    roles = naming.database_roles(key_sql)

    # Not every role truncates even at the largest permitted input: the role is
    # 5 + len(project_key) + len(suffix) bytes, so with a 48 character project
    # key only suffixes longer than 10 characters cross 63. `anon` lands at 57.
    truncated = {
        suffix: name
        for suffix, name in roles.items()
        if len(f"apg_{key_sql}_{suffix}") > naming.POSTGRES_IDENTIFIER_MAX
    }
    untruncated = {s: n for s, n in roles.items() if s not in truncated}

    assert set(untruncated) == {"anon"}, f"corpus assumption changed: {sorted(untruncated)}"
    # A literal rather than `len(ROLE_SUFFIXES) - 1`, deliberately: derived from
    # the tuple it is checking, this would agree with any future edit without
    # anyone reading it. Thirteen since Session 5 Run 7 added `api_documentation`.
    assert len(truncated) == 13

    # Every truncated role is exactly at the limit and carries its own
    # fingerprint. Shared fingerprints would mean one truncated prefix was
    # computed and per-role suffixes appended, which is the failure rule 9
    # forbids.
    fingerprints = {s: n[-naming.FINGERPRINT_LENGTH :] for s, n in truncated.items()}
    assert len(set(fingerprints.values())) == len(truncated), (
        f"roles share fingerprints, so they were not derived independently: {fingerprints}"
    )

    for name in truncated.values():
        assert len(name) == naming.POSTGRES_IDENTIFIER_MAX
    for name in untruncated.values():
        assert len(name) < naming.POSTGRES_IDENTIFIER_MAX


def test_longest_suffix_cannot_push_a_role_over_the_limit() -> None:
    key_sql = naming.sql_key(naming.project_key(MAX_SLUG, MAX_ENVIRONMENT))
    longest_suffix = max(naming.ROLE_SUFFIXES, key=len)
    assert longest_suffix == "postgrest_authenticator"

    untruncated = f"apg_{key_sql}_{longest_suffix}"
    assert len(untruncated) == 76, "corpus no longer exercises truncation"
    assert len(naming.database_role(key_sql, longest_suffix)) == 63


def test_fixtures_do_not_reach_the_truncation_boundary() -> None:
    """The fixture pair exercises collision, not truncation. Stated as a test."""
    lengths = {}
    for slug in ("fixture-alpha", "fixture-alpine"):
        key_sql = naming.sql_key(naming.project_key(slug, "dev"))
        roles = naming.database_roles(key_sql)
        lengths[slug] = max(len(name) for name in roles.values())
        # Untruncated: no name ends in the separator-plus-fingerprint shape.
        for name in roles.values():
            assert name == f"apg_{key_sql}_{_suffix_for(roles, name)}"

    assert lengths == {"fixture-alpha": 45, "fixture-alpine": 46}


def _suffix_for(roles: dict[str, str], name: str) -> str:
    return next(suffix for suffix, value in roles.items() if value == name)


# ---------------------------------------------------------------------------
# Property 2 — truncation format, fixed by golden vectors
# ---------------------------------------------------------------------------


def test_truncation_golden_vector() -> None:
    """Hard-coded expectations, so a refactor cannot silently change the rule.

    Deriving the expectation with hashlib inside the test would only prove the
    test agrees with itself.
    """
    result = naming.truncate("a" * 80, limit=63, context="demo", separator="-")
    assert result == "a" * 52 + "-" + "0d5e78657e"
    assert len(result) == 63
    assert naming.fingerprint("demo", "a" * 80) == "0d5e78657e"


def test_role_truncation_golden_vector() -> None:
    key_sql = naming.sql_key(naming.project_key(MAX_SLUG, MAX_ENVIRONMENT))
    assert naming.database_role(key_sql, "postgrest_authenticator") == (
        "apg_saaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_ebbbbbbbbbbbbbbb_998940bd80"
    )


def test_truncated_length_is_exactly_the_limit() -> None:
    for limit in (20, 40, 63):
        result = naming.truncate("z" * 200, limit=limit, context="c", separator="_")
        assert len(result) == limit
        assert result[-(naming.FINGERPRINT_LENGTH + 1)] == "_"


def test_values_at_or_below_the_limit_are_untouched() -> None:
    assert naming.truncate("a" * 63, limit=63, context="c", separator="-") == "a" * 63
    assert naming.truncate("short", limit=63, context="c", separator="-") == "short"


def test_long_shared_prefixes_do_not_collide() -> None:
    """The property `fixture-alpha`/`fixture-alpine` are a shallow instance of."""
    left = "p" * 60 + "aaa"
    right = "p" * 60 + "bbb"
    assert left[:52] == right[:52]

    a = naming.truncate(left, limit=63, context="ctx", separator="-")
    b = naming.truncate(right, limit=63, context="ctx", separator="-")
    assert a != b


def test_context_participates_in_the_fingerprint() -> None:
    value = "q" * 80
    assert naming.truncate(value, limit=63, context="one", separator="-") != naming.truncate(
        value, limit=63, context="two", separator="-"
    )


def test_non_ascii_is_rejected_rather_than_mis_measured() -> None:
    with pytest.raises(naming.NamingError, match="non-ASCII"):
        naming.truncate("é" * 80, limit=63, context="c", separator="-")


def test_limit_too_small_to_fingerprint_is_an_error() -> None:
    with pytest.raises(naming.NamingError, match="too small"):
        naming.truncate("a" * 40, limit=10, context="c", separator="-")


# ---------------------------------------------------------------------------
# Property 3 — determinism, including across processes
# ---------------------------------------------------------------------------

_SUBPROCESS_PROBE = """
import json, sys
sys.path.insert(0, %r)
from agentic_postgres import naming

identity = naming.derive(
    slug="fixture-alpha", environment="dev", domain="fixture-alpha-dev.test",
    api_base_path="/api", mcp_base_path="/mcp",
)
payload = {
    "roles": identity.roles,
    "fingerprint": naming.fingerprint("postgres_role", "a" * 90),
    "canonical": naming.canonical_json(
        {"z": 1, "a": {"n": [3, 2, 1]}, "m": "\\u00e9"}
    ).decode("utf-8"),
}
sys.stdout.write(json.dumps(payload, sort_keys=True))
"""


def _run_probe(hash_seed: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_PROBE % str(REPO_ROOT / "src")],
        capture_output=True,
        text=True,
        env={"PYTHONHASHSEED": hash_seed, "PATH": "/usr/bin:/bin"},
        check=True,
    )
    return json.loads(result.stdout)


def test_derivation_is_independent_of_pythonhashseed() -> None:
    """Runbook §3.7 rule 8 — no reliance on Python's randomized ``hash()``."""
    assert _run_probe("0") == _run_probe("1")


def test_canonical_json_is_byte_stable_across_processes() -> None:
    in_process = naming.canonical_json({"z": 1, "a": {"n": [3, 2, 1]}, "m": "é"}).decode()
    assert _run_probe("0")["canonical"] == in_process


def test_canonical_json_shape() -> None:
    data = {"z": 1, "a": {"nested": True}, "m": [3, 1, 2]}
    raw = naming.canonical_json(data)

    assert isinstance(raw, bytes)
    assert b"\r\n" not in raw, "CRLF would break byte-identical rendering"
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert json.loads(raw.decode("utf-8")) == data

    # The real sortedness property is that re-serializing the parsed document
    # with sort_keys reproduces the bytes exactly. Scanning lines for quoted
    # keys would conflate nested keys with top-level ones and assert nothing.
    round_tripped = (
        json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    assert raw == round_tripped

    top_level = list(json.loads(raw))
    assert top_level == sorted(top_level)


def test_canonical_json_is_repeatable_in_process() -> None:
    data = {"b": [1, 2], "a": {"x": None}}
    assert naming.canonical_json(data) == naming.canonical_json(dict(reversed(list(data.items()))))


def test_canonical_json_preserves_non_ascii_without_escaping() -> None:
    raw = naming.canonical_json({"note": "café"})
    assert "café" in raw.decode("utf-8")
    assert b"\\u00e9" not in raw


# ---------------------------------------------------------------------------
# The §3.8 derived identity table
# ---------------------------------------------------------------------------


@pytest.fixture
def alpha() -> naming.ProjectIdentity:
    return naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )


def test_derived_identity_matches_the_specified_table(alpha: naming.ProjectIdentity) -> None:
    assert alpha.key == "fixture-alpha-dev"
    assert alpha.sql_key == "fixture_alpha_dev"
    assert alpha.compose_project_name == "apg-fixture-alpha-dev"
    assert alpha.edge_network == "apg-fixture-alpha-dev-edge"
    assert alpha.internal_network == "apg-fixture-alpha-dev-internal"
    assert alpha.postgres_volume == "apg-fixture-alpha-dev-postgres"
    assert alpha.database_name == "fixture_alpha_dev"
    assert alpha.route_rest == "https://fixture-alpha-dev.test/api/rest"
    assert alpha.route_app == "https://fixture-alpha-dev.test/api/app"
    assert alpha.route_mcp == "https://fixture-alpha-dev.test/mcp"
    # The page, not the `/docs` root above it (ADR 0061). This replaces
    # `== ".../docs"` and is stricter rather than weaker: the old assertion was
    # satisfied by a document whose documentation route pointed one segment
    # above the only path anything had measured, which is what it was recording.
    assert alpha.route_docs == "https://fixture-alpha-dev.test/docs/rest"
    assert alpha.jwt_issuer == "https://fixture-alpha-dev.test/api/app/auth"
    assert alpha.jwt_audience == "urn:agentic-postgres:fixture-alpha:dev"
    assert alpha.secrets_namespace == "agentic-postgres/fixture-alpha-dev"
    # `apg-` since Run 3 (ADR 0105, D339): every other derived identifier here
    # carries the namespace and the bucket was the sole exception, while a
    # bucket's collision domain is the whole Cloudflare account rather than this
    # project. The PREFIX deliberately does NOT carry it -- it lives inside a
    # bucket this project already owns, so there is nothing to collide with.
    assert alpha.storage_bucket == "apg-fixture-alpha-dev"
    assert alpha.storage_prefix == "objects/fixture-alpha-dev/"
    assert alpha.backup_stanza == "fixture-alpha-dev"
    assert alpha.backup_repository_prefix == "pgbackrest/fixture-alpha-dev/"
    assert alpha.generated_directory == ".generated/fixture-alpha-dev"


def test_derived_roles_match_the_specified_names(alpha: naming.ProjectIdentity) -> None:
    assert alpha.roles["anon"] == "apg_fixture_alpha_dev_anon"
    assert alpha.roles["object_owner"] == "apg_fixture_alpha_dev_object_owner"
    assert alpha.roles["postgrest_authenticator"] == (
        "apg_fixture_alpha_dev_postgrest_authenticator"
    )


def test_explicit_values_override_computed_defaults() -> None:
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
        database_name="custom_db",
        storage_bucket="custom-bucket",
        storage_prefix="custom/prefix/",
        backup_stanza="custom-stanza",
        backup_repository_prefix="custom/backup/",
    )
    assert identity.database_name == "custom_db"
    assert identity.storage_bucket == "custom-bucket"
    assert identity.storage_prefix == "custom/prefix/"
    assert identity.backup_stanza == "custom-stanza"
    assert identity.backup_repository_prefix == "custom/backup/"


def test_disabled_features_derive_no_identity() -> None:
    identity = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
        storage_enabled=False,
        backup_enabled=False,
    )
    assert identity.storage_bucket is None
    assert identity.storage_prefix is None
    assert identity.backup_stanza is None
    assert identity.backup_repository_prefix is None


# ---------------------------------------------------------------------------
# Collision-isolation contract (runbook §8)
# ---------------------------------------------------------------------------


def test_fixture_identities_are_isolated() -> None:
    """Compares parsed semantic fields, never naive duplicate-string search."""
    alpha = naming.derive(
        slug="fixture-alpha",
        environment="dev",
        domain="fixture-alpha-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )
    alpine = naming.derive(
        slug="fixture-alpine",
        environment="dev",
        domain="fixture-alpine-dev.test",
        api_base_path="/api",
        mcp_base_path="/mcp",
    )

    must_differ = (
        "key",
        "sql_key",
        "compose_project_name",
        "edge_network",
        "internal_network",
        "postgres_volume",
        "database_name",
        "route_rest",
        "route_app",
        "route_mcp",
        "route_docs",
        "jwt_issuer",
        "jwt_audience",
        "secrets_namespace",
        "storage_bucket",
        "storage_prefix",
        "backup_stanza",
        "backup_repository_prefix",
        "generated_directory",
    )
    for name in must_differ:
        assert getattr(alpha, name) != getattr(alpine, name), f"{name} collides across fixtures"

    for suffix in naming.ROLE_SUFFIXES:
        assert alpha.roles[suffix] != alpine.roles[suffix], f"role {suffix} collides"

    assert not set(alpha.roles.values()) & set(alpine.roles.values())


# ---------------------------------------------------------------------------
# Output validators
# ---------------------------------------------------------------------------


def test_the_derived_bucket_is_namespaced_and_an_override_is_not() -> None:
    """ADR 0105 / D339, and both halves matter.

    A bucket's collision domain is the whole Cloudflare account, not this
    project, and the bucket was the only derived identifier here without the
    `apg` namespace every router, middleware and role carries. Measured rather
    than reasoned about: a real account already held `items`, `photos`,
    `pictures` and three more, which is exactly the namespace a bare
    `alpha-dev` sits in.

    The second assertion is the one that would be lost by "fixing" this
    symmetrically. An explicit override exists so an operator can point at a
    bucket named by a convention that is not ours, and prefixing it would make
    `bucket: my-existing-bucket` silently mean something else.
    """
    assert naming.storage_bucket_name("alpha-dev") == "apg-alpha-dev"
    assert naming.storage_bucket_name("alpha-dev", "my-existing-bucket") == "my-existing-bucket"

    # The prefix is deliberately NOT namespaced: it is scoped by a bucket this
    # project owns, so there is nothing to collide with.
    assert naming.storage_object_prefix("alpha-dev") == "objects/alpha-dev/"
    assert naming.storage_object_prefix("alpha-dev", "custom/") == "custom/"


def test_r2_bucket_rejects_names_that_violate_the_provider_rules() -> None:
    with pytest.raises(naming.NamingError):
        naming.r2_bucket("-leading-hyphen")
    with pytest.raises(naming.NamingError):
        naming.r2_bucket("trailing-hyphen-")
    with pytest.raises(naming.NamingError):
        naming.r2_bucket("ab")


def test_postgres_identifier_rejects_an_invalid_leading_character() -> None:
    with pytest.raises(naming.NamingError):
        naming.postgres_identifier("1nvalid", context="test")


def test_r2_bucket_truncation_stays_valid() -> None:
    result = naming.r2_bucket("b" * 90)
    assert len(result) == 63
    assert result[0].isalnum() and result[-1].isalnum()


# ---------------------------------------------------------------------------
# Session 14's metrics surface (ADR 0164)
# ---------------------------------------------------------------------------


def test_the_metrics_route_is_the_path_session_one_reserved() -> None:
    """The reservation and the route are one string, and this binds them.

    ADR 0005 reserved ``/metrics`` in Session 1; ADR 0164 redeems it in Session
    14. The characters now sit in two authorities: ``RESERVED_BASE_PATHS``
    holds the reservation, ``naming.METRICS_ROUTE_PATH`` holds the route. That
    is the same duplication ``DOCS_ROOT_PATH`` has always had with the same
    tuple, and it has never had a test.

    Move the route without moving the reservation and a project manifest can
    claim the path the platform serves on. Traefik then resolves the collision
    deterministically and invisibly in favour of the longer rule -- ADR 0005's
    third rejected alternative, arrived at by accident. Nothing else in this
    suite would notice.
    """
    from agentic_postgres import config

    assert naming.METRICS_ROUTE_PATH in config.RESERVED_BASE_PATHS


def test_the_metrics_surface_derives_one_router_and_credential_per_project() -> None:
    """Per project, because Traefik's middleware namespace is host-wide.

    Two projects sharing a credential middleware name share the credential, and
    the symptom is that one project's metrics password opens the other's
    telemetry. That is ``docs_credential_middleware_name``'s recorded failure
    in a new place, which is why this is derived rather than named.
    """
    assert naming.metrics_router_name("alpha-dev") != naming.metrics_router_name("beta-dev")

    alpha_auth = naming.metrics_credential_middleware_name("alpha-dev")
    beta_auth = naming.metrics_credential_middleware_name("beta-dev")
    assert alpha_auth != beta_auth

    # And the metrics credential is not the documentation credential. Sharing
    # would make rotating one silently rotate the other, and would hand a
    # monitoring system the documentation along with the scrape.
    assert alpha_auth != naming.docs_credential_middleware_name("alpha-dev")


def test_the_derived_metrics_route_matches_its_published_path(
    alpha: naming.ProjectIdentity,
) -> None:
    """URL and path from one expression, which is D177's repair.

    ``route_metrics`` is the address a reader is given; ``route_metrics_path``
    is what the router rule matches on. Derived twice they drift, and the drift
    stays invisible until somebody types the URL.
    """
    assert alpha.route_metrics_path == naming.METRICS_ROUTE_PATH
    assert alpha.route_metrics == f"https://fixture-alpha-dev.test{naming.METRICS_ROUTE_PATH}"
    assert alpha.metrics_router == naming.metrics_router_name(alpha.key)
    assert alpha.metrics_credential_middleware == naming.metrics_credential_middleware_name(
        alpha.key
    )
