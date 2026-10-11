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


@pytest.fixture(scope="module")
def public_documents(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The same two manifests with `database.public_endpoints` on (ADR 0268) --
    the shape a slot's manifest has -- rendered into a SANDBOX: these are not
    the gate's fixture renders, and nothing is published under `.generated/`."""
    import yaml

    base = tmp_path_factory.mktemp("public-endpoints")
    rendered = []
    with pytest.MonkeyPatch.context() as patch:
        generated = base / "generated"
        patch.setattr(rendering, "GENERATED_ROOT", generated)
        patch.setattr(rendering, "STAGING_ROOT", generated / ".staging")
        patch.setattr(rendering, "LOCK_ROOT", generated / ".locks")
        for manifest in ("project.example.yaml", "project.second.example.yaml"):
            document = yaml.safe_load((REPO_ROOT / manifest).read_text(encoding="utf-8"))
            document["database"]["public_endpoints"] = {"enabled": True}
            copy = base / manifest
            copy.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            directory = rendering.render_project(copy, REPO_ROOT / "capabilities.example.yaml")
            rendered.append(json.loads((directory / "outputs.json").read_text(encoding="utf-8")))
    return rendered[0], rendered[1]


#: Outputs v22 (ADR 0268). Null in both example renders -- no door -- so these
#: are asserted on `public_documents`, the same manifests with the facility on.
PUBLIC_POINTERS = (
    ("database", "public", "pooled", "host"),
    ("database", "public", "direct", "host"),
)

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
    # Session 10, outputs v13.
    ("backup", "bucket"),
    ("compose", "networks", "backup"),
    *PUBLIC_POINTERS,
)


def test_every_field_the_collision_evidence_checks_is_checked_here_too() -> None:
    """The two lists that had to agree and never met.

    ``MUST_DIFFER`` above and ``evidence.ISOLATED_FIELDS`` are both hand-written
    tuples of the same kind of thing, they are named together in a comment in
    ``output_migrations``, and **nothing compared them** until Session 10 added a
    field to both and noticed it could as easily have added it to one (D536).
    That is D174/D175's shape -- a property maintained by review rather than by
    a test -- and it fails silently in the worse direction: a name dropped from
    ``ISOLATED_FIELDS`` leaves the published ``collision_count`` reporting zero
    over a smaller set, which reads exactly like isolation.

    Containment rather than equality, and the surplus is pinned rather than
    waved at, so this cannot be satisfied by ``MUST_DIFFER`` growing something
    unrelated. ``ISOLATED_FIELDS`` is the set the shipped evidence document
    counts collisions over; ``MUST_DIFFER`` additionally covers values that are
    project-scoped but are not identities two projects could collide *on*.
    """
    from agentic_postgres.evidence import ISOLATED_FIELDS

    missing = sorted(set(ISOLATED_FIELDS) - set(MUST_DIFFER))
    assert not missing, f"ISOLATED_FIELDS checks these and this module does not: {missing}"

    surplus = sorted(set(MUST_DIFFER) - set(ISOLATED_FIELDS))
    assert surplus == [
        ("project", "slug"),
        ("routes", "app"),
        ("routes", "docs"),
        ("routes", "mcp"),
        ("routes", "rest"),
    ], (
        "MUST_DIFFER's surplus over ISOLATED_FIELDS moved. Adding an identity to "
        "one list and not the other is the defect this test exists for, so the "
        "difference is pinned rather than merely bounded."
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
    documents: tuple[dict[str, Any], dict[str, Any]],
    public_documents: tuple[dict[str, Any], dict[str, Any]],
    pointer: tuple[str, ...],
) -> None:
    alpha, alpine = public_documents if pointer in PUBLIC_POINTERS else documents
    assert at(alpha, pointer) is not None, f"{'.'.join(pointer)} is null: nothing compared"
    assert at(alpha, pointer) != at(alpine, pointer), f"{'.'.join(pointer)} collides"


def test_the_public_endpoints_are_derived_and_disjoint(
    documents: tuple[dict[str, Any], dict[str, Any]],
    public_documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Outputs v22 (ADR 0268, D2349): with the facility on, each project's two
    names are `pool.`/`direct.` + its own domain, its own customer roles and
    database, port 5432 and `verify-full` -- no URL, no password member at all.
    Off (the examples as committed), the block is `enabled: false` and two
    nulls, and every other member of the document is unchanged by the flag."""
    for document in public_documents:
        public = document["database"]["public"]
        domain = document["project"]["domain"]
        roles = document["database"]["roles"]
        assert public["enabled"] is True
        assert public["pooled"] == {
            "host": f"pool.{domain}", "port": 5432, "user": roles["customer_app"],
            "database": document["database"]["name"], "sslmode": "verify-full",
        }  # fmt: skip
        assert public["direct"] == {
            "host": f"direct.{domain}", "port": 5432, "user": roles["customer_admin"],
            "database": document["database"]["name"], "sslmode": "verify-full",
        }  # fmt: skip
    a, b = public_documents
    assert {a["database"]["public"][d]["host"] for d in ("pooled", "direct")}.isdisjoint(
        {b["database"]["public"][d]["host"] for d in ("pooled", "direct")}
    )
    for off, on in zip(documents, public_documents, strict=True):
        assert off["database"]["public"] == {"enabled": False, "pooled": None, "direct": None}
        assert {k: v for k, v in off["database"].items() if k != "public"} == {
            k: v for k, v in on["database"].items() if k != "public"
        }


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


def test_collision_count_is_zero(
    documents: tuple[dict[str, Any], dict[str, Any]],
    public_documents: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The single number the evidence file reports."""
    alpha, alpine = documents
    collisions = [
        ".".join(pointer)
        for pointer in MUST_DIFFER
        if pointer not in PUBLIC_POINTERS and at(alpha, pointer) == at(alpine, pointer)
    ]
    on_a, on_b = public_documents
    collisions += [
        ".".join(pointer) for pointer in PUBLIC_POINTERS if at(on_a, pointer) == at(on_b, pointer)
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
