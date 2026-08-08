"""Identity collision counting (ADR 0016).

``project_scoped_collision_count`` gates session evidence: non-zero and
``bin/write-session-evidence.py`` exits 5. It therefore has to mean exactly one
thing — two projects share a resource — and nothing adjacent to it.

The interesting case is the one Session 1 never reached. Two projects with
storage and backup disabled render ``null`` for four isolated fields. Comparing
those with ``==`` scored four collisions for two projects that share nothing, so
the first Session 2 deployment would have failed the gate at step 8 for a
correct system.

Both directions are tested. Loosening the comparison without the second test
would be indistinguishable from deleting the fields.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT
from agentic_postgres.deployed_output import SCHEMA_VERSION
from agentic_postgres.evidence import ISOLATED_FIELDS, at, collision_count

pytestmark = [pytest.mark.contract, pytest.mark.p0]

NULLABLE_FIELDS = (
    ("storage", "bucket"),
    ("storage", "prefix"),
    ("backup", "stanza"),
    ("backup", "repository_prefix"),
)


#: The project this repository renders from its own committed example manifest.
#: Named, not discovered -- see below.
FIXTURE_PROJECT = "fixture-alpha-dev"


def load_fixture() -> dict[str, Any]:
    """A real rendered document, used as the shape to vary from.

    A rendered document rather than a hand-written one, so a schema change
    surfaces here instead of leaving this module testing a shape the renderer no
    longer produces.

    **Named, not "the first thing in `.generated/`".** That is what this did, and
    it was green on a development machine for the reason that machine renders
    only the two committed fixtures. On the deployment host `.generated/` also
    holds `alpha-dev` and `beta-dev` -- real projects, rendered by the
    *previously installed release*, so schema v2 documents with no
    `database.container`. `sorted()` put one of them first and six tests failed
    with `KeyError: 'container'` on a host where nothing was wrong (D64).

    The shape being varied from has to come from this release. A directory
    listing is not a version, which is why the assertion below is not redundant
    with naming the directory.
    """
    outputs = REPO_ROOT / ".generated" / FIXTURE_PROJECT / "outputs.json"
    if not outputs.is_file():
        pytest.skip(f"{FIXTURE_PROJECT} is not rendered; run ./deploy.sh --render-only first")

    document = json.loads(outputs.read_text(encoding="utf-8"))
    assert document["schema_version"] == SCHEMA_VERSION, (
        f"{outputs} is schema v{document['schema_version']} and this release renders "
        f"v{SCHEMA_VERSION}; every test below would be varying a shape the renderer "
        "no longer produces"
    )
    return document


def test_a_document_from_an_older_release_is_refused_not_skipped(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """The general form of D64, asserted where it was actually wrong.

    `.generated/` is a by-product directory. On the deployment host it holds the
    real projects as the *previous* release rendered them, and `collision_count`
    reads a field that release did not emit. Skipping those would keep the count
    at `0` while silently removing a real project from it — the failure mode is
    an isolation check that means less than it did the run before and says
    nothing about the change.
    """
    from agentic_postgres import evidence

    generated = tmp_path / ".generated"
    (generated / "current-dev").mkdir(parents=True)
    (generated / "current-dev" / "outputs.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION}), encoding="utf-8"
    )
    (generated / "legacy-dev").mkdir()
    (generated / "legacy-dev" / "outputs.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION - 1}), encoding="utf-8"
    )

    monkeypatch.setattr(evidence, "REPO_ROOT", tmp_path)
    with pytest.raises(evidence.EvidenceError) as raised:
        evidence.load_rendered()

    message = str(raised.value)
    assert "legacy-dev" in message, "the refusal does not name the project to re-render"
    assert "--render-only" in message, "the refusal does not name the remedy"
    assert "current-dev" not in message


def put(document: dict[str, Any], pointer: tuple[str, ...], value: Any) -> None:
    target: Any = document
    for key in pointer[:-1]:
        target = target[key]
    target[pointer[-1]] = value


def with_values(document: dict[str, Any], suffix: str, nullable: list[Any]) -> dict[str, Any]:
    """A deep copy whose every isolated field is distinct, bar the four given.

    ``nullable`` supplies the storage and backup identifiers positionally, in
    ``NULLABLE_FIELDS`` order, so each test states exactly the case it means.
    """
    copy = json.loads(json.dumps(document))

    for pointer in ISOLATED_FIELDS:
        if pointer in NULLABLE_FIELDS:
            continue
        current = at(copy, pointer)
        if isinstance(current, str):
            put(copy, pointer, f"{current}-{suffix}")

    for role, name in copy["database"]["roles"].items():
        copy["database"]["roles"][role] = f"{name}-{suffix}"

    for pointer, value in zip(NULLABLE_FIELDS, nullable, strict=True):
        put(copy, pointer, value)

    return copy


# ---------------------------------------------------------------------------
# The change
# ---------------------------------------------------------------------------


def test_two_storage_disabled_projects_do_not_collide() -> None:
    """The case Session 2 is the first to reach."""
    document = load_fixture()
    left = with_values(document, "one", [None, None, None, None])
    right = with_values(document, "two", [None, None, None, None])

    for pointer in NULLABLE_FIELDS:
        assert at(left, pointer) is None and at(right, pointer) is None

    assert collision_count({"left": left, "right": right}) == 0


# ---------------------------------------------------------------------------
# Guard the guard — "ignore null pairs" must not become "ignore these fields"
# ---------------------------------------------------------------------------


def test_two_projects_sharing_a_bucket_still_collide() -> None:
    document = load_fixture()
    shared = "shared-bucket"
    left = with_values(document, "one", [shared, None, None, None])
    right = with_values(document, "two", [shared, None, None, None])

    assert collision_count({"left": left, "right": right}) == 1


def test_every_nullable_field_is_still_compared_when_populated() -> None:
    document = load_fixture()
    for index, pointer in enumerate(NULLABLE_FIELDS):
        values: list[Any] = [None, None, None, None]
        values[index] = "shared-value"
        left = with_values(document, "one", values)
        right = with_values(document, "two", values)
        assert collision_count({"left": left, "right": right}) == 1, (
            f"{'.'.join(pointer)} stopped being compared"
        )


def test_one_null_and_one_value_is_not_a_collision() -> None:
    """It never was equal; this asserts the exemption did not widen."""
    document = load_fixture()
    left = with_values(document, "one", ["a-bucket", None, None, None])
    right = with_values(document, "two", [None, None, None, None])
    assert collision_count({"left": left, "right": right}) == 0


def test_a_shared_role_name_is_still_a_collision() -> None:
    """Roles get no null exemption; all thirteen are always derived."""
    document = load_fixture()
    left = with_values(document, "one", [None, None, None, None])
    right = with_values(document, "two", [None, None, None, None])

    role = next(iter(right["database"]["roles"]))
    right["database"]["roles"][role] = left["database"]["roles"][role]

    assert collision_count({"left": left, "right": right}) == 1


def test_a_single_project_has_no_pairs_to_compare() -> None:
    document = load_fixture()
    assert collision_count({"only": with_values(document, "one", [None] * 4)}) == 0
