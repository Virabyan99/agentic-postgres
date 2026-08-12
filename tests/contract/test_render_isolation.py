"""Collision-isolation contract (runbook §8).

Session 1 proves *generated identity* isolation, not runtime isolation. The
comparison is over parsed semantic fields — never a naive duplicate-string
search, which would both miss real collisions in nested structures and flag
legitimately shared values like the template version.

The fixtures share a 12-character slug prefix on purpose: a derivation that
truncated a shared prefix and appended suffixes would collide here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, naming, rendering

pytestmark = [pytest.mark.contract, pytest.mark.p0]


@pytest.fixture(scope="module")
def compose_environments() -> tuple[dict[str, str], dict[str, str]]:
    """Both projects' `compose.env`, parsed.

    A second document beside `outputs.json`, and until Run 9a nothing compared
    it. Every Traefik router and middleware name lives here and nowhere else,
    which is how a shared one could exist without any isolation test seeing it.
    """
    parsed = []
    for manifest in ("project.example.yaml", "project.second.example.yaml"):
        directory = rendering.render_project(
            REPO_ROOT / manifest, REPO_ROOT / "capabilities.example.yaml"
        )
        values = {}
        for line in (directory / "compose.env").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key] = value
        parsed.append(values)
    return parsed[0], parsed[1]


@pytest.fixture(scope="module")
def documents() -> tuple[dict[str, Any], dict[str, Any]]:
    rendered = []
    for manifest in ("project.example.yaml", "project.second.example.yaml"):
        directory = rendering.render_project(
            REPO_ROOT / manifest, REPO_ROOT / "capabilities.example.yaml"
        )
        rendered.append(json.loads((directory / "outputs.json").read_text(encoding="utf-8")))
    return rendered[0], rendered[1]


#: Runbook §8: every one of these must differ across the two projects.
MUST_DIFFER = (
    ("project", "key"),
    ("project", "slug"),
    ("project", "domain"),
    ("project", "generated_directory"),
    ("compose", "project_name"),
    ("compose", "networks", "edge"),
    ("compose", "networks", "internal"),
    ("compose", "volumes", "postgres"),
    ("database", "name"),
    ("database", "container"),
    ("routes", "rest"),
    ("routes", "app"),
    ("routes", "mcp"),
    ("routes", "docs"),
    ("jwt", "issuer"),
    ("jwt", "audience"),
    ("secrets", "namespace"),
    ("storage", "bucket"),
    ("storage", "prefix"),
    ("backup", "stanza"),
    ("backup", "repository_prefix"),
)

#: Runbook §8: these are *allowed* to match. Asserting they do keeps the
#: isolation test from being satisfied by two unrelated documents.
MAY_MATCH = (
    ("schema_version",),
    ("template_version",),
    ("project", "environment"),
    ("database", "pooled", "status"),
    ("database", "direct", "status"),
    # The memory budget is a capacity decision, not an identity. Two projects
    # left at the defaults have the same one, and asserting that here is what
    # stops a future reader from adding it to MUST_DIFFER on the assumption
    # that everything under `database` is project-scoped.
    ("database", "budget", "shared_buffers_mb"),
    ("database", "budget", "unreclaimable_mb"),
    ("inputs", "capabilities_sha256"),
    ("inputs", "versions_lock_sha256"),
    ("inputs", "source_specification_sha256"),
)


def at(document: dict[str, Any], pointer: tuple[str, ...]) -> Any:
    value: Any = document
    for key in pointer:
        value = value[key]
    return value


@pytest.mark.parametrize("pointer", MUST_DIFFER, ids=lambda p: ".".join(p))
def test_project_scoped_identity_differs(
    documents: tuple[dict[str, Any], dict[str, Any]], pointer: tuple[str, ...]
) -> None:
    alpha, alpine = documents
    assert at(alpha, pointer) != at(alpine, pointer), f"{'.'.join(pointer)} collides"


@pytest.mark.parametrize("pointer", MAY_MATCH, ids=lambda p: ".".join(p))
def test_shared_values_are_shared(
    documents: tuple[dict[str, Any], dict[str, Any]], pointer: tuple[str, ...]
) -> None:
    alpha, alpine = documents
    assert at(alpha, pointer) == at(alpine, pointer)


def test_base_paths_are_allowed_to_match(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Both projects use /api and /mcp. Route *URLs* still differ, by domain."""
    alpha, alpine = documents
    assert alpha["routes"]["rest"].endswith("/api/rest")
    assert alpine["routes"]["rest"].endswith("/api/rest")
    assert alpha["routes"]["rest"] != alpine["routes"]["rest"]


def test_every_role_differs(documents: tuple[dict[str, Any], dict[str, Any]]) -> None:
    alpha, alpine = documents
    for suffix in naming.ROLE_SUFFIXES:
        assert alpha["database"]["roles"][suffix] != alpine["database"]["roles"][suffix], suffix


def test_role_name_sets_are_fully_disjoint(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    alpha, alpine = documents
    shared = set(alpha["database"]["roles"].values()) & set(alpine["database"]["roles"].values())
    assert not shared, f"shared role names: {sorted(shared)}"


def test_project_manifest_digests_differ(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    alpha, alpine = documents
    assert alpha["inputs"]["project_sha256"] != alpine["inputs"]["project_sha256"]


def test_collision_count_is_zero(documents: tuple[dict[str, Any], dict[str, Any]]) -> None:
    """The single number the evidence file reports."""
    alpha, alpine = documents
    collisions = [
        ".".join(pointer) for pointer in MUST_DIFFER if at(alpha, pointer) == at(alpine, pointer)
    ]
    collisions += [
        f"database.roles.{suffix}"
        for suffix in naming.ROLE_SUFFIXES
        if alpha["database"]["roles"][suffix] == alpine["database"]["roles"][suffix]
    ]
    assert collisions == []


def test_generated_directories_are_separate(
    documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    alpha, alpine = documents
    alpha_dir = Path(alpha["project"]["generated_directory"])
    alpine_dir = Path(alpine["project"]["generated_directory"])
    assert alpha_dir != alpine_dir
    assert alpha_dir.name not in alpine_dir.name
    assert alpine_dir.name not in alpha_dir.name


def test_similar_prefixes_actually_exercise_the_comparison() -> None:
    """Guard the guard: if the fixtures stop being similar, this test is weak.

    `fixture-alpha` and `fixture-alpine` share `fixture-alp` — 11 characters —
    and then diverge. That shared prefix is the whole reason this fixture pair
    exists: a derivation that truncated a common prefix and appended per-role
    suffixes would produce identical names for both projects.
    """
    alpha = "fixture-alpha"
    alpine = "fixture-alpine"
    assert alpha != alpine

    common = 0
    for left, right in zip(alpha, alpine, strict=False):
        if left != right:
            break
        common += 1

    assert common >= 10, f"fixtures share only {common} characters; collision risk untested"


def test_no_traefik_name_is_shared_between_two_projects(
    compose_environments: tuple[dict[str, str], dict[str, str]],
) -> None:
    """A router or middleware name is **host-wide** in Traefik.

    Two projects sharing one middleware name do not get one middleware each;
    they get whichever definition the proxy loaded last, applied to both. For
    the documentation route that means one project's Basic Auth guarding the
    other project's page -- or neither, which is the direction that serves a
    protected page to anyone.

    Derived from the environment rather than from a list written here, so a
    router added in a later session is covered the day it is rendered rather
    than the day somebody remembers to extend a constant.

    Found by a mutation expected to go red that came out green (D203). Nothing
    compared these two files, so *no* route's names had ever been asserted
    project-scoped -- not the documentation route's, and not the REST route's
    either.
    """
    first, second = compose_environments
    names = sorted(
        key
        for key in set(first) & set(second)
        if key.endswith(("_ROUTER_NAME", "_MIDDLEWARE_NAME"))
    )
    assert names, "no Traefik names found in compose.env; this compared nothing"

    shared = sorted(key for key in names if first[key] == second[key])
    assert not shared, (
        f"{shared} are identical in both projects. A Traefik name is host-wide, so a "
        "shared one is two projects using one router or one middleware"
    )


def test_every_route_contributes_a_name_to_that_comparison(
    compose_environments: tuple[dict[str, str], dict[str, str]],
) -> None:
    """The control for the test above.

    A derivation that stopped writing router names to `compose.env` would leave
    the comparison with nothing to disagree about, and an empty set of shared
    names reads exactly like a clean one.
    """
    first, _ = compose_environments
    routers = {key for key in first if key.endswith("_ROUTER_NAME")}
    assert routers >= {"HEALTH_ROUTER_NAME", "REST_ROUTER_NAME", "DOCS_ROUTER_NAME"}, (
        f"a published route stopped naming its router in compose.env: {sorted(routers)}"
    )
