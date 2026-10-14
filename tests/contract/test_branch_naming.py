"""A branch's names (Session 40, ADR 0271, D2423, D2428, D2462).

Every name of a branch derives from one stem, `apg-<key>_<branch>`. The
underscore is the argument: a project key may hold a hyphen anywhere, so a
hyphenated stem could be another project's, and a key never holds `_`. These
proofs hold the derivation and, over generated and adversarial keys, that no
branch name equals any name a project or a restore drill derives.
"""

from __future__ import annotations

import dataclasses
import random
import string

import pytest

from agentic_postgres import naming

pytestmark = [pytest.mark.contract, pytest.mark.p0]

KEY = "slot3-prod"
DOMAIN = "slot3.agenticpostgresql.com"


def _project_names(slug: str, environment: str) -> set[str]:
    """Every string a project's identity derives, plus its customer doors and
    routers and one drill's names -- the names a branch must never take."""
    identity = naming.derive(
        slug=slug,
        environment=environment,
        domain="project.example.org",
        api_base_path="/api",
        mcp_base_path="/mcp",
        database_name="app",
    )
    key = identity.key
    names = {
        value for value in dataclasses.asdict(identity).values() if isinstance(value, str) and value
    }
    names |= set(naming.customer_pooler_containers(key))
    names |= {naming.customer_pool_router_name(key), naming.customer_direct_router_name(key)}
    names |= set(naming.project_router_names(key))
    names |= {
        naming.compose_project_name(key),
        naming.postgres_volume_name(key),
        naming.store_volume_name(key),
        naming.backup_network_name(key),
    }
    drill = naming.restore_drill_names(key, "2026101408185ab9")
    names |= {drill.volume, drill.container, drill.restore_container}
    return names


def test_every_branch_name_derives_from_one_stem() -> None:
    """Each resource is the stem plus its role, through `compose_name` (or the
    branch router validator), and a long key is truncated with a fingerprint
    rather than refused or allowed past 63.

    Goes red if: any name stops deriving from `apg-<key>_<branch>`, two
    resources of one branch collapse, or a name passes 63 characters."""
    names = naming.branch_names(KEY, "dev")
    assert names.stem == "apg-slot3-prod_dev"
    assert names.compose_project == "apg-slot3-prod_dev"
    assert names.volume == "apg-slot3-prod_dev-postgres"
    assert names.edge_network == "apg-slot3-prod_dev-edge"
    assert names.internal_network == "apg-slot3-prod_dev-internal"
    assert names.postgres_container == "apg-slot3-prod_dev-postgres-1"
    assert names.pool_container == "apg-slot3-prod_dev-customer-pool-1"
    assert names.direct_container == "apg-slot3-prod_dev-customer-direct-1"
    assert names.restore_container == "apg-slot3-prod_dev-pgbackrest"
    assert names.recovery_container == "apg-slot3-prod_dev-recovery"
    assert names.pool_router == "apg-slot3-prod_dev-customer-pool"
    assert names.direct_router == "apg-slot3-prod_dev-customer-direct"
    assert len(set(names.all_resources())) == len(names.all_resources())

    long_key = f"{'a' * 31}-{'b' * 16}"
    long_names = naming.branch_names(long_key, "abcdefghijkl")
    every = (*long_names.all_resources(), long_names.pool_router, long_names.direct_router)
    assert all(len(name) <= naming.COMPOSE_NAME_MAX for name in every), every
    assert len(set(every)) == len(every), every


def _legal(slug: str, environment: str) -> bool:
    """Is this a key a project can have? The set of legal keys is what
    `naming.derive` accepts (a slug ending in `-` derives an invalid bucket)."""
    try:
        _project_names(slug, environment)
    except naming.NamingError:
        return False
    return True


def _keys() -> list[tuple[str, str]]:
    """Adversarial (slug, environment) pairs -- the keys that would have
    collided with a hyphenated stem -- and the generated ones `derive` accepts."""
    adversarial = [
        ("slot3", "prod"),
        ("slot3", "prod-dev"),
        ("slot3", "prod-br-dev"),
        ("slot3-prod", "dev"),
        ("slot3-prod-br", "dev"),
        ("slot3-prod", "dev-postgres"),
        ("slot3-prod", "restore-dev"),
        ("slot3-prod-dev", "customer-pool"),
    ]
    rng = random.Random(40)  # noqa: S311 -- a reproducible property sample, not a secret
    alphabet = string.ascii_lowercase + string.digits + "-"
    generated = []
    for _ in range(300):
        slug = rng.choice(string.ascii_lowercase) + "".join(
            rng.choice(alphabet) for _ in range(rng.randint(2, 30))
        )
        environment = rng.choice(string.ascii_lowercase) + "".join(
            rng.choice(alphabet) for _ in range(rng.randint(1, 15))
        )
        if _legal(slug, environment):
            generated.append((slug, environment))
    assert len(generated) >= 100, f"only {len(generated)} generated keys were legal"
    assert all(_legal(*pair) for pair in adversarial)
    return adversarial + generated


def test_no_branch_stem_equals_a_project_or_drill_stem() -> None:
    """For every key in the sample and every branch of it, no branch resource or
    router equals any name ANY project of the sample derives -- its own included
    -- or any of their drills'.

    Goes red if: the stem's separator becomes one a key may hold (`-`): then
    `slot3-prod` + `dev` and the project `slot3-prod-dev` derive the same names."""
    keys = _keys()
    taken: set[str] = set()
    for slug, environment in keys:
        taken |= _project_names(slug, environment)
    for slug, environment in keys:
        key = f"{slug}-{environment}"
        for branch in ("dev", "qa1", "postgres", "pool"):
            names = naming.branch_names(key, branch)
            mine = {*names.all_resources(), names.compose_project, names.pool_router,
                    names.direct_router}  # fmt: skip
            clash = mine & taken
            assert not clash, (key, branch, sorted(clash))


@pytest.mark.parametrize(
    "bad",
    ["main", "", "a", "Dev", "dev-1", "dev_1", "1dev", "abcdefghijklm", "../x", "dev.x", "dév"],
)
def test_the_branch_name_rule_refuses_main_and_bad_names(bad: str) -> None:
    """`main` is the project (D2440); a name holds no separator, no capital, no
    dot, starts with a letter and is 2-12 characters. Each is refused with
    `NamingError` by every derivation that takes a branch."""
    with pytest.raises(naming.NamingError):
        naming.validate_branch_name(bad)
    with pytest.raises(naming.NamingError):
        naming.branch_names(KEY, bad)
    with pytest.raises(naming.NamingError):
        naming.branch_endpoint_hosts(DOMAIN, bad)


@pytest.mark.parametrize("good", ["dev", "qa1", "ab", "abcdefghijkl", "main2"])
def test_the_branch_name_rule_accepts_a_name(good: str) -> None:
    assert naming.validate_branch_name(good) == good


def test_the_branch_hosts_derive_from_the_domain() -> None:
    """`<branch>.pool.<domain>` and `<branch>.direct.<domain>`, below the
    project's own two names (the two wildcards, D2428); past 253 refused."""
    assert naming.branch_endpoint_hosts(DOMAIN, "dev") == (
        "dev.pool.slot3.agenticpostgresql.com",
        "dev.direct.slot3.agenticpostgresql.com",
    )
    pool, direct = naming.endpoint_hosts(DOMAIN)
    assert naming.branch_endpoint_hosts(DOMAIN, "dev") == (f"dev.{pool}", f"dev.{direct}")
    # 242 characters: `direct.<domain>` is 249 and fits; `<12>.direct.<domain>` is 262.
    long_domain = ".".join(["a" * 59] * 4) + ".io"
    assert len(long_domain) == 242
    naming.endpoint_hosts(long_domain)  # the project's own names still fit
    with pytest.raises(naming.NamingError, match="253"):
        naming.branch_endpoint_hosts(long_domain, "abcdefghijkl")


def test_a_branch_router_may_hold_the_separator_and_a_project_router_may_not() -> None:
    """D2462 (rig 40e): the branch's TCP routers carry the `_`, through their own
    validator; the project's router charset, which the collector's scrape filter
    interpolates (ADR 0167), is unchanged and still refuses it."""
    names = naming.branch_names(KEY, "dev")
    assert "_" in names.pool_router and "_" in names.direct_router
    assert naming.BRANCH_ROUTER_NAME_PATTERN.match(names.pool_router)
    assert not naming.TRAEFIK_NAME_PATTERN.match(names.pool_router)
    with pytest.raises(naming.NamingError):
        naming.traefik_name("apg-slot3-prod_dev-x", context="test")
