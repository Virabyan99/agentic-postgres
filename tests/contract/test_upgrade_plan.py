"""What an upgrade would do, computed before anything is mutated (ADR 0162).

The module is pure, so all of this runs in a checkout. One test reaches for the
rendered fixture, because a differ proved only against documents its own author
wrote is a differ proved against its author's idea of the shape (question 6).
"""

from __future__ import annotations

import json

import pytest
from rendered_fixtures import (  # type: ignore[import-not-found]
    FIXTURE_KEYS,
    fixture_dir,
    needs_rendered_fixtures,
)

from agentic_postgres import upgrade_plan as up

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def rendered(**overrides: object) -> dict:
    """A minimal document of the right kind. Small on purpose.

    The real shape is exercised by `test_the_plan_handles_the_real_rendered_shape`;
    these are for the logic, where 108 leaves would hide which one mattered.
    """
    document = {
        "document_kind": "rendered",
        "schema_version": 13,
        "template_version": "0.1.0-dev",
        "inputs": {
            "project_sha256": "a" * 64,
            "capabilities_sha256": "b" * 64,
            "secrets_contract_sha256": "c" * 64,
            "versions_lock_sha256": "d" * 64,
            "source_specification_sha256": "e" * 64,
        },
        "secrets": {"required_names": ["one", "two"]},
        "capabilities": {"enabled": []},
    }
    document.update(overrides)
    return document


# ---------------------------------------------------------------------------
# The walker
# ---------------------------------------------------------------------------


def test_leaves_keys_every_scalar_by_dotted_path() -> None:
    assert up.leaves({"a": {"b": 1}, "c": "x"}) == {"a.b": 1, "c": "x"}


def test_leaves_keeps_list_indices() -> None:
    """Position is meaningful in the one list that matters: the key set."""
    assert up.leaves({"kids": ["p", "q"]}) == {"kids[0]": "p", "kids[1]": "q"}


def test_the_matrix_and_the_plan_share_one_walker() -> None:
    """D725. Two copies would drift, and the matrix is a green Session 12 proof.

    Asserted by identity rather than by behaviour: two functions that happen to
    agree today are still two functions.
    """
    import importlib.util

    from agentic_postgres import REPO_ROOT

    path = REPO_ROOT / "tests" / "deployment" / "test_session12_isolation_matrix.py"
    spec = importlib.util.spec_from_file_location("_matrix_under_test", path)
    assert spec and spec.loader
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)

    assert matrix._leaves is up.leaves


# ---------------------------------------------------------------------------
# The difference set
# ---------------------------------------------------------------------------


def test_a_changed_leaf_is_reported_with_both_sides() -> None:
    found = up.differences(rendered(), rendered(template_version="0.2.0"))
    assert [(d.path, d.installed, d.candidate) for d in found] == [
        ("template_version", "0.1.0-dev", "0.2.0")
    ]


def test_additions_and_removals_are_reported_and_distinguishable() -> None:
    left = rendered(capabilities={"enabled": ["query_notes"]})
    right = rendered()
    right["secrets"]["required_names"] = ["one", "two", "three"]
    del right["capabilities"]

    found = {d.path: d for d in up.differences(left, right)}
    assert found["secrets.required_names[2]"].added
    assert not found["secrets.required_names[2]"].removed
    assert found["capabilities.enabled[0]"].removed


def test_an_empty_container_produces_no_leaf_and_so_its_arrival_is_invisible() -> None:
    """A measured limitation of the shared walker, asserted rather than left to
    be discovered.

    `leaves()` descends into dicts and lists and emits only scalars, so `{}` and
    `[]` produce nothing at all. A document that gains `capabilities: {enabled:
    []}` therefore differs in no leaf. It has never mattered for the isolation
    matrix, and it is stated here because an upgrade plan is a second reader of
    the same walker.

    **Not repaired in Run 4**: emitting a leaf for an empty container would give
    the Session 12 matrix new paths to classify, and `test_every_leaf_is_classified`
    is a green host proof. Changing a shared walker to suit its newer caller is
    how the older one breaks (D725).
    """
    assert up.leaves({"a": [], "b": {}, "c": 1}) == {"c": 1}
    assert up.differences({"x": 1}, {"x": 1, "empty": []}) == ()


def test_a_legitimate_null_is_not_confused_with_absence() -> None:
    """D600's family, and the reason `ABSENT` is a sentinel rather than `None`.

    `jwt.retire_after` is `null` whenever no rotation is in flight. If absence
    were spelled `None`, a document that dropped the field and one that carried
    it as null would be indistinguishable -- and the plan would report the wrong
    one of two very different situations.
    """
    carries_null = rendered(jwt={"retire_after": None})
    lacks_it = rendered()

    found = {d.path: d for d in up.differences(lacks_it, carries_null)}
    assert found["jwt.retire_after"].added
    assert found["jwt.retire_after"].installed == up.Difference.ABSENT
    assert found["jwt.retire_after"].candidate is None

    # And two documents that both carry it as null differ in nothing.
    assert up.differences(carries_null, rendered(jwt={"retire_after": None})) == ()


def test_differences_are_sorted_by_path() -> None:
    """A plan an operator reads twice must read the same way twice."""
    right = rendered(template_version="0.2.0")
    right["inputs"]["versions_lock_sha256"] = "f" * 64
    paths = [d.path for d in up.differences(rendered(), right)]
    assert paths == sorted(paths)


# ---------------------------------------------------------------------------
# What the documents can establish by themselves
# ---------------------------------------------------------------------------


def test_a_moved_version_lock_is_an_image_digest_change() -> None:
    right = rendered()
    right["inputs"]["versions_lock_sha256"] = "f" * 64
    assert up.classify_document_changes(up.differences(rendered(), right)) == ("image_digest",)


def test_a_new_required_secret_is_derivable_and_is_major() -> None:
    from agentic_postgres import compatibility

    right = rendered()
    right["secrets"]["required_names"] = ["one", "two", "three"]
    classes = up.classify_document_changes(up.differences(rendered(), right))
    assert "secret_required_added" in classes
    assert compatibility.required_level(list(classes)) == compatibility.MAJOR


def test_it_does_not_invent_the_classes_it_cannot_see() -> None:
    """A released migration lives in `released.lock.json` and an API change in
    `contracts/`. Neither is in a rendered document, so neither is guessed.

    A function that inferred `migration_added` from a `schema_version` move would
    be answering a question it cannot see the evidence for.
    """
    right = rendered(schema_version=14)
    classes = up.classify_document_changes(up.differences(rendered(), right))
    assert "migration_added" not in classes
    assert not any(name.startswith("api_operation") for name in classes)


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def test_a_missing_installed_document_is_undetermined_and_blocks() -> None:
    """ADR 0162 §4. A left-hand side nobody read is not "no changes detected"."""
    plan = up.build_plan(None, rendered())
    assert plan.verdict == up.UNDETERMINED
    assert plan.blocks
    assert plan.reasons and "nobody looked" in plan.reasons[0]


def test_a_missing_candidate_is_undetermined() -> None:
    plan = up.build_plan(rendered(), None)
    assert plan.verdict == up.UNDETERMINED
    assert plan.blocks


def test_a_deployed_document_on_either_side_is_undetermined() -> None:
    """D732/D733: the kinds share 41% of their vocabulary and the deployed one
    has no `inputs` block. Comparing them would produce a plausible wrong answer,
    so it is refused by kind rather than attempted."""
    deployed = rendered(document_kind="deployed")
    for pair in ((deployed, rendered()), (rendered(), deployed)):
        plan = up.build_plan(*pair)
        assert plan.verdict == up.UNDETERMINED
        assert "not 'rendered'" in plan.reasons[0]


def test_an_upgrade_that_moves_the_operators_inputs_is_blocked() -> None:
    """An upgrade changes the release, not the manifests the operator supplies."""
    right = rendered(template_version="0.2.0")
    right["inputs"]["project_sha256"] = "9" * 64
    plan = up.build_plan(rendered(), right)

    assert plan.verdict == up.BLOCKED
    assert plan.operator_digests_moved == ("project_sha256",)
    assert "the operator's own inputs moved" in plan.reasons[0]


def test_a_candidate_that_is_not_ahead_is_blocked() -> None:
    plan = up.build_plan(rendered(), rendered())
    assert plan.verdict == up.BLOCKED
    assert plan.bump is None
    assert "not ahead" in plan.reasons[0]


def test_a_patch_bump_cannot_carry_a_change_that_needs_minor() -> None:
    plan = up.build_plan(
        rendered(template_version="1.0.0"),
        rendered(template_version="1.0.1"),
        also=("migration_added",),
    )
    assert plan.verdict == up.BLOCKED
    assert plan.bump == "patch"
    assert plan.required == "minor"
    assert "require minor" in plan.reasons[0]


def test_a_minor_bump_carrying_a_migration_is_permitted() -> None:
    plan = up.build_plan(
        rendered(template_version="1.0.0"),
        rendered(template_version="1.1.0"),
        also=("migration_added",),
    )
    assert plan.verdict == up.OK
    assert not plan.blocks
    assert plan.reasons == ()


def test_the_run_seven_bump_is_permitted_for_an_image_move() -> None:
    """`0.1.0-dev -> 0.2.0` is this session's own bump, asserted rather than
    assumed to be legal under the rules this session wrote."""
    right = rendered(template_version="0.2.0")
    right["inputs"]["versions_lock_sha256"] = "f" * 64
    plan = up.build_plan(rendered(), right)
    assert plan.verdict == up.OK
    assert plan.bump == "minor"
    assert plan.required == "patch"


def test_an_unclassified_extra_change_raises_rather_than_passing() -> None:
    with pytest.raises(up.UpgradePlanError):
        up.build_plan(rendered(), rendered(template_version="0.2.0"), also=("invented",))


def test_an_unparseable_version_is_undetermined_not_blocked() -> None:
    """The distinction matters: `blocked` says the upgrade is wrong, and
    `undetermined` says nobody could tell. A version this release cannot read is
    the second."""
    plan = up.build_plan(rendered(template_version="banana"), rendered(template_version="0.2.0"))
    assert plan.verdict == up.UNDETERMINED
    assert "could not be parsed" in plan.reasons[0]


def test_every_non_ok_plan_says_why() -> None:
    """A refusal that does not name its reason sends an operator to read source."""
    blocked = [
        up.build_plan(None, rendered()),
        up.build_plan(rendered(), None),
        up.build_plan(rendered(), rendered()),
        up.build_plan(rendered(document_kind="deployed"), rendered()),
    ]
    for plan in blocked:
        assert plan.blocks
        assert plan.reasons, plan


# ---------------------------------------------------------------------------
# Against the shape the renderer actually produces
# ---------------------------------------------------------------------------


@needs_rendered_fixtures
def test_the_plan_handles_the_real_rendered_shape() -> None:
    """Question 6: a differ proved only against documents its own author wrote is
    proved against its author's idea of the shape.

    The fixture is the renderer's own output, 108 leaves. Compared with itself it
    must find nothing and block for the one honest reason -- which also pins the
    measured determinism: a renderer that had produced a timestamp would make
    this fail with differences rather than with "not ahead".
    """
    document = json.loads(
        (fixture_dir(FIXTURE_KEYS[0]) / "outputs.json").read_text(encoding="utf-8")
    )
    assert document["document_kind"] == "rendered"
    assert len(up.leaves(document)) > 50, "the fixture is smaller than expected"

    plan = up.build_plan(document, document)
    assert plan.differences == ()
    assert plan.verdict == up.BLOCKED
    assert "not ahead" in plan.reasons[0]
