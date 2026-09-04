"""Project-local capability profiles (ADR 0183): a profile may only narrow.

**D867 named the failure mode before the run started**: *"this is the feature
most likely to be built as a general override mechanism, because that is what
'profile' means everywhere else."* So the load-bearing tests here are the ones
that hand the compiler a profile that would WIDEN a bound -- every field, in the
direction that is wide for that field -- and assert a refusal at compile time
with no lock written. A test that only showed a narrowing being applied would be
asserting that the mechanism works, which an override mechanism also does.

Nothing here reaches a database or a network. `apply_profile` is pure, the CLI
arms run `bin/mcp-contract.py` in a subprocess against temporary manifests, and
the runtime arm loads a lock the real compiler wrote.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT, api_surface, capability_compiler, config, openapi_normalize
from agentic_postgres.capability_compiler import PROFILE_FIELDS, CompilerError, apply_profile
from app import mcp_lock

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CANONICAL = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
SNAPSHOT = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
MANIFEST = REPO_ROOT / "capabilities.example.yaml"
PROJECTS = (REPO_ROOT / "project.example.yaml", REPO_ROOT / "project.second.example.yaml")

SOURCES = {
    "capabilities_sha256": "a" * 64,
    "api_surface_sha256": "b" * 64,
    "canonical_openapi_sha256": "c" * 64,
    "project_manifest_sha256": "d" * 64,
}


@pytest.fixture(scope="module")
def canonical() -> dict[str, Any]:
    """The APPROVED contract, exactly as the CLI reads it."""
    return json.loads(CANONICAL.read_text("utf-8"))


@pytest.fixture(scope="module")
def profiles() -> dict[str, dict[str, Any]]:
    return {path.name: config.load_project_manifest(path)["mcp"]["profile"] for path in PROJECTS}


def tool(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in document["tools"] if entry["name"] == name)


def project_manifest(tmp_path: Path, mutate: Any) -> Path:
    """A copy of the alpha fixture with `mutate(document)` applied, on disk."""
    document = yaml.safe_load(PROJECTS[0].read_text("utf-8"))
    mutate(document)
    path = tmp_path / "project.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def contract_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "mcp-contract.py"), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


# ---------------------------------------------------------------------------
# The shipped fixtures exercise the feature (D927, D884)
# ---------------------------------------------------------------------------


def test_the_shipped_fixtures_narrow_something_and_differ(
    canonical: dict[str, Any], profiles: dict[str, dict[str, Any]]
) -> None:
    """A field declared before its behaviour defaults to off (D927), and a pair
    of fixtures that agree cannot prove a value is read (D884). Both example
    manifests carry a non-empty profile, both compile, both change at least
    one tool, and the two profiles are not the same profile."""
    assert len(profiles) == 2
    for name, profile in profiles.items():
        assert profile, f"{name} declares an empty profile; the feature would ship inert"
        narrowed = apply_profile(canonical, profile)
        assert narrowed["tools"] != canonical["tools"], f"{name}'s profile changed nothing"
    first, second = profiles.values()
    assert first != second, "the two fixtures agree, so neither proves the other is read"


def test_a_profile_changes_exactly_what_it_names_and_nothing_else(
    canonical: dict[str, Any], profiles: dict[str, dict[str, Any]]
) -> None:
    """The narrowed contract differs from the approved one in exactly the
    fields the profile names -- `max_rows` on every resource and on the tool --
    and the input is not mutated. An override mechanism that also touched a
    neighbour would pass a test that only read the named fields."""
    profile = profiles["project.second.example.yaml"]
    before = copy.deepcopy(canonical)
    narrowed = apply_profile(canonical, profile)
    assert canonical == before, "apply_profile mutated its input"

    for entry in canonical["tools"]:
        original, changed = entry, tool(narrowed, entry["name"])
        expected = profile.get(entry["name"], {})
        moved = {key for key in original if original[key] != changed[key]}
        moved |= {key for key in changed if key not in original}
        if "max_rows" in expected:
            assert moved == (set(expected) | {"resources"}), (entry["name"], moved)
            assert all(r["max_rows"] == expected["max_rows"] for r in changed["resources"])
        else:
            assert moved == set(expected), (entry["name"], moved)
        for field, value in expected.items():
            if field != "max_rows":
                assert changed[field] == value


# ---------------------------------------------------------------------------
# Every field, in its wide direction, is refused (D867)
# ---------------------------------------------------------------------------


#: One tool of an applicable kind per field, from the approved contract.
SUBJECT = {
    "timeout_ms": "list_resources",
    "max_response_bytes": "query_resource",
    "max_concurrent_calls": "query_resource",
    "max_rows": "query_resource",
    "max_affected_rows": "create_note",
    "supports_dry_run": "create_note",
    "requires_approval": "update_task_status",
}


BOOLEAN_FIELDS = ("supports_dry_run", "requires_approval")
NUMERIC_FIELDS = tuple(sorted(field for field in PROFILE_FIELDS if field not in BOOLEAN_FIELDS))


@pytest.mark.parametrize("field", NUMERIC_FIELDS)
def test_each_numeric_field_is_refused_one_above_and_accepted_at_and_below(
    canonical: dict[str, Any], field: str
) -> None:
    """Three arms per numeric field, and the middle one is the control.

    Widened by exactly one: refused, and the message says WIDEN and names the
    tool and field. Equal: accepted, and narrows nothing. One below: accepted,
    and the narrowed contract carries the profile's value. The booleans have
    their own test, because "one above" means nothing for them -- and the two
    lists partition the roster, asserted so a new field cannot fall between.
    """
    assert set(NUMERIC_FIELDS) | set(BOOLEAN_FIELDS) == set(PROFILE_FIELDS)
    name = SUBJECT[field]
    subject = tool(canonical, name)
    compiled = (
        min(r["max_rows"] for r in subject["resources"]) if field == "max_rows" else subject[field]
    )

    with pytest.raises(CompilerError, match=rf"WIDEN {name}\.{field}"):
        apply_profile(canonical, {name: {field: compiled + 1}})

    equal = apply_profile(canonical, {name: {field: compiled}})
    assert equal["tools"] == canonical["tools"], "an equal profile changed something"

    if compiled > 1:
        narrowed = apply_profile(canonical, {name: {field: compiled - 1}})
        changed = tool(narrowed, name)
        carried = (
            {r["max_rows"] for r in changed["resources"]} | {changed["max_rows"]}
            if field == "max_rows"
            else {changed[field]}
        )
        assert carried == {compiled - 1}, (field, carried)


def test_the_two_booleans_have_opposite_polarity(canonical: dict[str, Any]) -> None:
    """`supports_dry_run` is a permission and `requires_approval` a restriction
    (D925), so "narrow" points the opposite way for each -- and a profile that
    got either backwards would GRANT something.

    The approved contract supports a dry run and requires no approval, so the
    refused direction for each has to be constructed: a contract that does NOT
    support a dry run refuses a profile that says it does, and one that DOES
    require approval refuses a profile that lifts it.
    """
    assert tool(canonical, "create_note")["supports_dry_run"] is True
    assert tool(canonical, "update_task_status")["requires_approval"] is False

    # Narrow direction, against the shipped contract: accepted and applied.
    off = apply_profile(canonical, {"create_note": {"supports_dry_run": False}})
    assert tool(off, "create_note")["supports_dry_run"] is False
    on = apply_profile(canonical, {"update_task_status": {"requires_approval": True}})
    assert tool(on, "update_task_status")["requires_approval"] is True

    # Equal: accepted, nothing moves.
    assert apply_profile(canonical, {"create_note": {"supports_dry_run": True}}) == canonical
    assert (
        apply_profile(canonical, {"update_task_status": {"requires_approval": False}}) == canonical
    )

    # Wide direction, against a constructed contract: refused.
    stricter = copy.deepcopy(canonical)
    tool(stricter, "create_note")["supports_dry_run"] = False
    tool(stricter, "update_task_status")["requires_approval"] = True
    with pytest.raises(CompilerError, match=r"WIDEN create_note\.supports_dry_run"):
        apply_profile(stricter, {"create_note": {"supports_dry_run": True}})
    with pytest.raises(CompilerError, match=r"WIDEN update_task_status\.requires_approval"):
        apply_profile(stricter, {"update_task_status": {"requires_approval": False}})


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("list_resources", "max_response_bytes"),
        ("list_resources", "max_concurrent_calls"),
        ("list_resources", "max_rows"),
        ("create_note", "max_rows"),
        ("query_resource", "max_affected_rows"),
        ("query_resource", "supports_dry_run"),
        ("run_report", "requires_approval"),
    ],
)
def test_a_field_on_a_kind_that_does_not_carry_it_is_refused(
    canonical: dict[str, Any], name: str, field: str
) -> None:
    """A bound on nothing reads exactly like a real one (ADR 0179's rule for
    metadata capabilities, applied to the profile). The value is the narrowest
    the schema permits, so the refusal cannot be about widening."""
    value = False if field == "supports_dry_run" else True if field == "requires_approval" else 1
    with pytest.raises(CompilerError, match=rf"{name}\.{field}.*carries no {field}"):
        apply_profile(canonical, {name: {field: value}})

    # The control: the same tool accepts a field its kind does carry.
    accepted = apply_profile(canonical, {name: {"timeout_ms": 100}})
    assert tool(accepted, name)["timeout_ms"] == 100


def test_an_unknown_tool_an_unknown_field_and_an_empty_entry_are_refused(
    canonical: dict[str, Any],
) -> None:
    with pytest.raises(CompilerError, match="delete_everything"):
        apply_profile(canonical, {"delete_everything": {"timeout_ms": 100}})
    with pytest.raises(CompilerError, match="not a bound the runtime reads"):
        apply_profile(canonical, {"query_resource": {"columns": ["id"]}})
    with pytest.raises(CompilerError, match="narrows nothing"):
        apply_profile(canonical, {"query_resource": {}})
    # And the empty PROFILE is not an empty entry: a project that narrows
    # nothing, stated, compiles the approved contract unchanged.
    assert apply_profile(canonical, {}) == canonical


def test_max_rows_is_checked_against_every_resource_not_the_widest(
    canonical: dict[str, Any],
) -> None:
    """Built as a case where the two resources DISAGREE, because the shipped
    contract gives `notes` and `tasks` the same number and D884 is what happens
    when an aggregate is only ever reached with inputs that agree. A per-tool
    value above the smaller resource is a widening of that resource, and a
    clamp against it would have accepted the value silently."""
    uneven = copy.deepcopy(canonical)
    resources = {r["name"]: r for r in tool(uneven, "query_resource")["resources"]}
    resources["tasks"]["max_rows"] = 50
    assert resources["notes"]["max_rows"] != 50, "the resources agree; the case cannot tell"

    with pytest.raises(CompilerError, match=r"resource 'tasks'"):
        apply_profile(uneven, {"query_resource": {"max_rows": 100}})

    narrowed = tool(apply_profile(uneven, {"query_resource": {"max_rows": 50}}), "query_resource")
    assert {r["max_rows"] for r in narrowed["resources"]} == {50}
    assert narrowed["max_rows"] == 50, "the tool's own max_rows was not re-derived"


def test_a_profile_cannot_introduce_a_bound_the_contracts_version_lacks() -> None:
    """A v1 contract declares no `max_response_bytes`; a profile naming it would
    be introducing the bound early rather than narrowing one (ADR 0177). The
    control narrows `timeout_ms`, which every version carries."""
    manifest = config.load_capabilities_manifest(MANIFEST)
    manifest["schema_version"] = 1
    for entry in manifest["capabilities"]:
        for field in (
            *capability_compiler.VERSIONED_FIELDS,
            *capability_compiler.BUDGET_FIELDS,
            *capability_compiler.WRITE_DECLARATIONS,
        ):
            entry.pop(field, None)
    v1 = capability_compiler.compile_canonical(
        capabilities=manifest,
        surface=api_surface.load_surface(),
        published_objects=openapi_normalize.declared_objects(json.loads(SNAPSHOT.read_text())),
    )
    assert v1["schema_version"] == 1
    assert "max_response_bytes" not in tool(v1, "query_resource")

    with pytest.raises(CompilerError, match="does not declare"):
        apply_profile(v1, {"query_resource": {"max_response_bytes": 1024}})
    assert (
        tool(apply_profile(v1, {"query_resource": {"timeout_ms": 100}}), "query_resource")[
            "timeout_ms"
        ]
        == 100
    )


# ---------------------------------------------------------------------------
# The lock records it; the digest stays the approved contract's
# ---------------------------------------------------------------------------


def test_the_lock_records_the_profile_and_keeps_the_approved_digest(
    canonical: dict[str, Any], profiles: dict[str, dict[str, Any]]
) -> None:
    """`canonical_sha256` is what the audit row records as `contract_hash` and
    what the deployed document publishes, and both name the REVIEWED contract.
    The profile block is the whole difference between that and the tools."""
    profile = profiles["project.second.example.yaml"]
    lock = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpine-dev",
        upstream="https://fixture-alpine-dev.test/api/rest",
        sources=SOURCES,
        profile=profile,
    )
    approved = sha256(capability_compiler.canonical_bytes(canonical)).hexdigest()
    assert lock["canonical_sha256"] == approved
    assert lock["tools"] == apply_profile(canonical, profile)["tools"]
    assert lock["tools"] != canonical["tools"]
    assert lock["profile"] == profile
    assert set(lock["compiled_from"]) == set(SOURCES)

    # Without the manifest digest the profile is an input nobody can identify.
    with pytest.raises(CompilerError, match="project_manifest_sha256"):
        capability_compiler.compile_lock(
            canonical=canonical,
            project_key="fixture-alpine-dev",
            upstream="https://fixture-alpine-dev.test/api/rest",
            sources={k: v for k, v in SOURCES.items() if k != "project_manifest_sha256"},
            profile=profile,
        )

    # No profile: no key, and the tools are the approved ones. Absent, not null.
    plain = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpha-dev",
        upstream="https://fixture-alpha-dev.test/api/rest",
        sources=SOURCES,
    )
    assert "profile" not in plain
    assert plain["tools"] == canonical["tools"]


# ---------------------------------------------------------------------------
# The roster is the set of bounds the runtime reads (D486's arrangement)
# ---------------------------------------------------------------------------


def test_the_roster_is_the_runtimes_and_every_member_is_a_bound_the_runtime_reads() -> None:
    """Two copies, one test between them. And each member is a field the
    runtime's parsed lock carries -- on the tool, on a resource, or on the
    write -- so the profile cannot name a value the runtime does not hold.

    The control is `columns`: a resource field the runtime reads and the roster
    deliberately excludes (ADR 0183), so a roster that grew to cover every
    parsed field would fail here rather than quietly admitting the allowlists.
    """
    assert set(PROFILE_FIELDS) == set(mcp_lock.PROFILE_FIELDS)
    parsed = (
        {field.name for field in dataclasses.fields(mcp_lock.Tool)}
        | {field.name for field in dataclasses.fields(mcp_lock.Resource)}
        | {field.name for field in dataclasses.fields(mcp_lock.WriteSpec)}
    )
    assert set(PROFILE_FIELDS) <= parsed
    assert "columns" in parsed and "columns" not in PROFILE_FIELDS

    runtime = "".join(
        (REPO_ROOT / "services" / "auth-api" / "app" / name).read_text("utf-8")
        for name in ("mcp_tools.py", "mcp_query.py")
    )
    for field in PROFILE_FIELDS:
        assert f".{field}" in runtime, f"nothing in the runtime reads {field}"
    for field, rule in PROFILE_FIELDS.items():
        assert set(rule["kinds"]) <= {"metadata", "read", "write"}, field


# ---------------------------------------------------------------------------
# The runtime reads the block, and refuses a lock that disagrees with it
# ---------------------------------------------------------------------------


def test_the_runtime_loads_a_profiled_lock_and_refuses_one_that_disagrees(
    tmp_path: Path, canonical: dict[str, Any], profiles: dict[str, dict[str, Any]]
) -> None:
    """The reader (D816). A lock the real compiler wrote loads and reports its
    profile; the same lock with one tool's value put back is refused, because
    the compiler sets every profiled field EQUAL to the profile's value."""
    profile = profiles["project.second.example.yaml"]
    document = capability_compiler.compile_lock(
        canonical=canonical,
        project_key="fixture-alpine-dev",
        upstream="https://fixture-alpine-dev.test/api/rest",
        sources=SOURCES,
        profile=profile,
    )

    def load(mutate: Any) -> mcp_lock.CapabilityLock:
        copied = copy.deepcopy(document)
        mutate(copied)
        path = tmp_path / f"lock-{len(list(tmp_path.iterdir()))}.json"
        path.write_bytes(capability_compiler.canonical_bytes(copied))
        return mcp_lock.load_lock(path)

    loaded = load(lambda d: None)
    assert loaded.profile == profile
    assert loaded.tool("create_note").supports_dry_run is False
    assert loaded.tool("update_task_status").requires_approval is True
    assert {r.max_rows for r in loaded.tool("query_resource").resources} == {50}
    assert loaded.tool("run_report").timeout_ms == 2000

    def restore_dry_run(d: dict[str, Any]) -> None:
        tool(d, "create_note")["supports_dry_run"] = True

    with pytest.raises(mcp_lock.LockError, match="disagreeing with its own profile"):
        load(restore_dry_run)

    def restore_one_resource(d: dict[str, Any]) -> None:
        tool(d, "query_resource")["resources"][0]["max_rows"] = 200

    with pytest.raises(mcp_lock.LockError, match=r"query_resource\.max_rows"):
        load(restore_one_resource)

    def unknown_tool(d: dict[str, Any]) -> None:
        d["profile"]["delete_everything"] = {"timeout_ms": 100}

    with pytest.raises(mcp_lock.LockError, match="delete_everything"):
        load(unknown_tool)

    def unknown_field(d: dict[str, Any]) -> None:
        d["profile"]["query_resource"]["columns"] = ["id"]

    with pytest.raises(mcp_lock.LockError, match="not a bound this runtime reads"):
        load(unknown_field)

    def no_profile(d: dict[str, Any]) -> None:
        del d["profile"]
        d["tools"] = copy.deepcopy(canonical["tools"])

    assert load(no_profile).profile is None, "a version 1 project's lock reports no profile"


# ---------------------------------------------------------------------------
# Compile time: the CLI, and the deploy that calls it
# ---------------------------------------------------------------------------


def test_check_refuses_a_widening_profile_at_compile_time(tmp_path: Path) -> None:
    """The sentence in the plan: a profile that would widen any bound fails
    `mcp-contract.sh check`. Exit 5 -- the contract code, not argparse's 2 --
    and the message says so. The control is the shipped fixture, which narrows
    and exits 0 saying what it narrowed."""

    def widen(document: dict[str, Any]) -> None:
        document["mcp"]["profile"]["query_resource"]["max_rows"] = 201

    refused = contract_cli("check", "--project", str(project_manifest(tmp_path, widen)))
    assert refused.returncode == 5, refused.stderr
    assert "WIDEN query_resource.max_rows" in refused.stderr, refused.stderr

    accepted = contract_cli("check", "--project", str(PROJECTS[0]))
    assert accepted.returncode == 0, accepted.stderr
    assert "narrows the approved contract" in accepted.stdout
    assert "query_resource.max_rows" in accepted.stdout


def test_lock_requires_the_project_manifest(tmp_path: Path) -> None:
    """Required, not optional: a lock compiled without the profile would ignore
    it and report success (D927's shape). Both the Python command and the shell
    wrapper refuse, with exit 2, before any input is read."""
    outputs = tmp_path / "outputs.json"
    outputs.write_text(
        json.dumps(
            {"project": {"key": "probe-dev"}, "routes": {"rest": "https://x.test/api/rest"}}
        ),
        encoding="utf-8",
    )
    python = contract_cli("lock", "--outputs", str(outputs))
    assert python.returncode == 2
    assert "--project" in python.stderr

    shell = subprocess.run(
        [str(REPO_ROOT / "bin" / "mcp-contract.sh"), "lock", "--outputs", str(outputs)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert shell.returncode == 2
    assert "requires --project" in shell.stderr

    # The control: with the manifest, the lock compiles and carries the profile.
    ok = contract_cli("lock", "--outputs", str(outputs), "--project", str(PROJECTS[1]))
    assert ok.returncode == 0, ok.stderr
    lock = json.loads(ok.stdout)
    assert lock["profile"] == config.load_project_manifest(PROJECTS[1])["mcp"]["profile"]
    assert (
        lock["compiled_from"]["project_manifest_sha256"]
        == sha256(PROJECTS[1].read_bytes()).hexdigest()
    )


def test_the_deploy_hands_the_lock_the_installed_manifest() -> None:
    """The deploy passes `--project`, and it passes the INSTALLED copy -- the
    one step 6 hands to the bootstrap and the migrator -- so the profile and
    the digest are of the document this deploy actually installed."""
    source = (REPO_ROOT / "bin" / "deploy-project.py").read_text(encoding="utf-8")
    lock_call = source[source.index('"mcp-contract.sh"') :]
    lock_call = lock_call[: lock_call.index("lock_path.write_text")]
    assert '"--project"' in lock_call
    assert 'state_directory / "manifest.yaml"' in lock_call
    assert "arguments.project" not in lock_call, "the lock digests the operator's copy"


# ---------------------------------------------------------------------------
# The schema: the ranges mirror the capability schema's, and the doc reaches them
# ---------------------------------------------------------------------------


def test_the_profile_ranges_mirror_the_capability_schemas() -> None:
    """A profile cannot even ASK for more than a capability may declare. The
    real refusal is the comparison against the compiled contract, which no
    schema can express; this keeps the two documents from disagreeing about
    the envelope."""
    project = json.loads((REPO_ROOT / "schemas" / "project.schema.json").read_text("utf-8"))
    capability = json.loads((REPO_ROOT / "schemas" / "capabilities.schema.json").read_text("utf-8"))
    entry = project["$defs"]["profileEntry"]["properties"]
    declared = capability["$defs"]["capability"]["properties"]
    assert set(entry) == set(PROFILE_FIELDS)
    for field in ("timeout_ms", "max_response_bytes", "max_concurrent_calls", "max_rows"):
        assert entry[field]["minimum"] == declared[field]["minimum"], field
        assert entry[field]["maximum"] == declared[field]["maximum"], field
    assert entry["max_affected_rows"]["maximum"] == declared["max_affected_rows"]["maximum"]


def test_the_bounds_table_reaches_the_profile() -> None:
    """D932. `bounds_table` walked `properties` and `$ref` and not
    `patternProperties`, so the profile's five numeric bounds would have been
    missing from a table that still looked complete -- ADR 0007's failure mode,
    through the generator, for the second time."""
    fields = {row["field"] for row in config.bounds_table()}
    numeric = {f for f in PROFILE_FIELDS if f not in ("supports_dry_run", "requires_approval")}
    assert {f"mcp.profile.<tool>.{field}" for field in numeric} <= fields
    # The version 1 fields are still bounded at version 1, and still documented.
    assert {"mcp.max_result_rows", "mcp.max_response_bytes"} <= fields
