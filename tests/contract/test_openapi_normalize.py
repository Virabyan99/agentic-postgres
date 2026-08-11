"""Normalizing a served OpenAPI document into the form two projects can share.

The fixture is not hand-written. `tests/fixtures/postgrest-openapi.captured.json`
is the document the locked PostgREST actually served, captured in Run 7 from a
cluster carrying the surface `contracts/postgrest-api-surface.yaml` describes,
with `openapi-server-proxy-uri` set the way a deployment sets it. Writing the
fixture by hand would have tested the normalizer against the document its author
imagined, which is the failure ADR 0019 exists for.

Each test below states what would have to break for it to go red, because
several of them assert a *substitution*, and a substitution is satisfied by any
implementation that overwrites enough.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, openapi_normalize
from agentic_postgres.openapi_normalize import (
    SENTINEL_BASE_PATH,
    SENTINEL_HOST,
    NormalizationError,
    canonical_bytes,
    declared_objects,
    fingerprint,
    load_document,
    normalize,
    sort_maps,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0]

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "postgrest-openapi.captured.json"

#: What the capture was taken behind. Not a guess: they are the two values the
#: rig passed as `openapi-server-proxy-uri`, and the document echoed them back.
CAPTURED_HOST = "alpha.example.test:443"
CAPTURED_BASE_PATH = "/api/rest"


@pytest.fixture
def served() -> dict[str, Any]:
    return load_document(FIXTURE.read_bytes())


def normalized(document: dict[str, Any]) -> dict[str, Any]:
    return normalize(document, expected_host=CAPTURED_HOST, expected_base_path=CAPTURED_BASE_PATH)


# ---------------------------------------------------------------------------
# The control
# ---------------------------------------------------------------------------


def test_the_fixture_is_a_real_captured_document(served: dict[str, Any]) -> None:
    """The control for everything below.

    Goes red if the fixture is replaced by something that is not a served
    PostgREST document -- at which point every refusal below could be passing
    because the input was already unusable rather than because the rule works.
    """
    assert served["swagger"] == "2.0"
    assert served["info"]["title"] == "PostgREST API"
    assert served["host"] == CAPTURED_HOST
    assert served["basePath"] == CAPTURED_BASE_PATH
    assert set(served["paths"]) == {
        "/",
        "/notes",
        "/tasks",
        "/rpc/create_note",
        "/rpc/update_task_status",
    }


def test_the_captured_document_is_not_already_sorted(served: dict[str, Any]) -> None:
    """Otherwise `sort_maps` is asserting something about an already-sorted input.

    Measured: PostgREST emits hash order, so `/tasks` precedes `/notes`. If a
    future capture happens to arrive sorted, this goes red and the sorting tests
    below stop being evidence of anything -- which is the signal to say so
    rather than to delete this.
    """
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert list(raw["paths"]) != sorted(raw["paths"])


# ---------------------------------------------------------------------------
# Substitution -- ADR 0050's "validate the real values, then substitute"
# ---------------------------------------------------------------------------


def test_the_two_project_specific_fields_become_sentinels(served: dict[str, Any]) -> None:
    result = normalized(served)
    assert result["host"] == SENTINEL_HOST
    assert result["basePath"] == SENTINEL_BASE_PATH


def test_nothing_but_those_fields_changes(served: dict[str, Any]) -> None:
    """The other half of the substitution, and the half a test usually forgets.

    Goes red if the normalizer starts rewriting content -- dropping a path,
    renaming a definition, collapsing a parameter. A test that only checked the
    sentinels would pass against a normalizer that returned nothing else at all.
    """
    result = normalized(served)
    for key in set(served) - {"host", "basePath", "schemes"}:
        assert result[key] == sort_maps(served[key]), f"{key} was altered"


def test_a_document_whose_host_is_not_the_published_one_is_refused(
    served: dict[str, Any],
) -> None:
    """The capture-without-a-proxy-URI case, which is what actually happens.

    Measured: with no `openapi-server-proxy-uri`, the document carries the
    container's bind address `0.0.0.0:3000`. Substituting a sentinel over it
    would produce a snapshot that matches while describing a service nobody can
    reach at the published address.
    """
    served["host"] = "0.0.0.0:3000"
    with pytest.raises(NormalizationError, match="publishes host"):
        normalized(served)


def test_a_document_whose_base_path_is_not_the_published_one_is_refused(
    served: dict[str, Any],
) -> None:
    served["basePath"] = "/"
    with pytest.raises(NormalizationError, match="publishes basePath"):
        normalized(served)


def test_a_document_offering_cleartext_is_refused(served: dict[str, Any]) -> None:
    """`schemes` is asserted rather than substituted, and this is why.

    A capture taken straight off the container carries `["http"]`. Replacing it
    with `["https"]` unread would write a snapshot claiming a transport the
    captured service never offered.
    """
    served["schemes"] = ["http"]
    with pytest.raises(NormalizationError, match="schemes"):
        normalized(served)


def test_normalizing_without_the_expected_values_is_refused(served: dict[str, Any]) -> None:
    with pytest.raises(NormalizationError, match="both required"):
        normalize(served, expected_host="", expected_base_path=CAPTURED_BASE_PATH)


def test_a_project_value_surviving_elsewhere_is_refused(served: dict[str, Any]) -> None:
    """The guard on the substitution.

    Plants the project's hostname where nothing substitutes it -- inside a
    description PostgREST built from a SQL comment. Goes red the day the
    normalizer stops scanning for residue, which is the day a project's hostname
    can reach a file both projects compare against.
    """
    served["paths"]["/notes"]["get"]["description"] = f"See https://{CAPTURED_HOST}/api/rest"
    with pytest.raises(NormalizationError, match="survives in the normalized document"):
        normalized(served)


def test_the_residue_scan_finds_a_bare_hostname_too(served: dict[str, Any]) -> None:
    """Without the port, which is the form a `$ref` or an example would carry."""
    served["info"]["description"] = "Served from alpha.example.test"
    with pytest.raises(NormalizationError, match="survives in the normalized document"):
        normalized(served)


# ---------------------------------------------------------------------------
# Sorting: maps yes, arrays never
# ---------------------------------------------------------------------------


def test_every_map_is_sorted(served: dict[str, Any]) -> None:
    result = normalized(served)

    def walk(node: Any, where: str) -> None:
        if isinstance(node, dict):
            assert list(node) == sorted(node), f"{where} is not sorted"
            for key, value in node.items():
                walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{where}[{index}]")

    walk(result, "$")


def test_an_enum_keeps_its_declared_order(served: dict[str, Any]) -> None:
    """The load-bearing half of the sort, and the one a careless fix would break.

    `api.task_status` is published in `enumsortorder`. The surface contract calls
    the comparison order-sensitive because a reordering passes a set comparison
    and changes what every generated client lists first. Goes red the moment
    `sort_maps` starts sorting arrays as well as maps.
    """
    before = served["definitions"]["tasks"]["properties"]["status"]["enum"]
    assert before == ["pending", "in_progress", "completed", "cancelled"]
    after = normalized(served)["definitions"]["tasks"]["properties"]["status"]["enum"]
    assert after == before


def test_a_required_argument_list_keeps_its_order(served: dict[str, Any]) -> None:
    """The second order-sensitive array, for the same reason and a different key."""
    body = served["paths"]["/rpc/update_task_status"]["post"]["parameters"][0]
    before = list(body["schema"]["required"])
    assert before == ["p_task_id", "p_expected_status", "p_new_status"]
    after = normalized(served)["paths"]["/rpc/update_task_status"]["post"]["parameters"][0]
    assert after["schema"]["required"] == before


def test_sorting_reorders_no_array_at_all() -> None:
    """Stated on a value built for it, so the rule is asserted and not sampled."""
    assert sort_maps({"b": [3, 1, 2], "a": {"z": ["x", "b", "a"]}}) == {
        "a": {"z": ["x", "b", "a"]},
        "b": [3, 1, 2],
    }


# ---------------------------------------------------------------------------
# Strict parsing
# ---------------------------------------------------------------------------


def test_a_duplicate_key_is_refused() -> None:
    """`json.loads` keeps the last one and says nothing.

    A document carrying `paths` twice would be normalized down to whichever copy
    came second, and every object in the other copy would be served and absent
    from everything that reviews it.
    """
    with pytest.raises(NormalizationError, match="duplicate key"):
        load_document('{"swagger": "2.0", "paths": {}, "paths": {"/x": {}}}')


def test_a_duplicate_key_deeper_in_the_document_is_refused() -> None:
    with pytest.raises(NormalizationError, match="duplicate key"):
        load_document('{"paths": {"/x": {"get": 1, "get": 2}}}')


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_a_non_json_constant_is_refused(constant: str) -> None:
    """Python accepts all three and writes them back out, producing a file no
    other parser will read -- including every client generator downstream."""
    with pytest.raises(NormalizationError, match="not JSON"):
        load_document(f'{{"swagger": "2.0", "x": {constant}}}')


def test_a_non_object_root_is_refused() -> None:
    with pytest.raises(NormalizationError, match="root is list"):
        load_document("[1, 2, 3]")


def test_a_document_over_the_size_bound_is_refused() -> None:
    with pytest.raises(NormalizationError, match="over the"):
        load_document(b"{}" + b" " * openapi_normalize.MAX_DOCUMENT_BYTES)


def test_bytes_that_are_not_json_are_refused() -> None:
    with pytest.raises(NormalizationError, match="not JSON"):
        load_document("<html>404</html>")


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_a_document_in_another_format_is_refused(served: dict[str, Any]) -> None:
    """An OpenAPI 3 document has none of the fields this module was measured on."""
    served["swagger"] = "3.0.0"
    with pytest.raises(NormalizationError, match="announces swagger"):
        normalized(served)


def test_an_unknown_top_level_key_is_refused(served: dict[str, Any]) -> None:
    """A PostgREST upgrade is expected to fail here, and that is the point.

    Goes red if `KNOWN_TOP_LEVEL` is widened to make an upgrade pass instead of
    re-measuring what the new version emits.
    """
    served["security"] = []
    with pytest.raises(NormalizationError, match="never seen"):
        normalized(served)


def test_a_missing_required_key_is_refused(served: dict[str, Any]) -> None:
    del served["paths"]
    with pytest.raises(NormalizationError, match="no \\['paths'\\]"):
        normalized(served)


def test_a_missing_project_specific_field_is_refused(served: dict[str, Any]) -> None:
    """A sentinel written into an absent field would make every project's
    document agree about a value none of them published."""
    del served["host"]
    with pytest.raises(NormalizationError, match="nothing to substitute"):
        normalized(served)


# ---------------------------------------------------------------------------
# The canonical form
# ---------------------------------------------------------------------------


def test_two_projects_normalize_to_the_same_bytes(served: dict[str, Any]) -> None:
    """ADR 0050's "two projects share one canonical snapshot", asserted.

    The second document is the first with the other project's published address,
    which is the only thing that differs between two deployments of this
    repository. Goes red if a project-specific value starts reaching the
    canonical form.
    """
    other = json.loads(json.dumps(served))
    other["host"] = "beta.example.test:443"
    other["basePath"] = "/beta/rest"

    first = canonical_bytes(normalized(served))
    second = canonical_bytes(
        normalize(other, expected_host="beta.example.test:443", expected_base_path="/beta/rest")
    )
    assert first == second


def test_the_canonical_form_is_stable_under_a_key_permutation(
    served: dict[str, Any],
) -> None:
    """The same document written in a different order is the same snapshot.

    This is what makes the committed file survive a PostgREST that reorders its
    hash map -- measured stable for a given key set, and nothing promises it
    stays that way.
    """
    permuted = {key: served[key] for key in reversed(list(served))}
    assert canonical_bytes(normalized(permuted)) == canonical_bytes(normalized(served))


def test_the_canonical_form_ends_in_exactly_one_newline(served: dict[str, Any]) -> None:
    payload = canonical_bytes(normalized(served))
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")
    assert b"\r" not in payload


def test_the_canonical_form_reparses(served: dict[str, Any]) -> None:
    result = normalized(served)
    assert load_document(canonical_bytes(result)) == result


def test_the_fingerprint_moves_when_the_surface_moves(served: dict[str, Any]) -> None:
    """What `API-CACHE-001` compares across a reload."""
    before = fingerprint(normalized(served))
    served["paths"]["/rpc/added_by_a_migration"] = {"post": {"tags": ["(rpc) added"]}}
    assert fingerprint(normalized(served)) != before


def test_the_fingerprint_does_not_move_when_only_the_address_does(served: dict[str, Any]) -> None:
    """The other half. A redeployment at a different host is not a DDL change,
    and a fingerprint that moved for one would make `API-CACHE-001` pass for the
    wrong reason."""
    other = json.loads(json.dumps(served))
    other["host"] = "beta.example.test:443"
    other["basePath"] = "/beta/rest"
    assert fingerprint(
        normalize(other, expected_host="beta.example.test:443", expected_base_path="/beta/rest")
    ) == fingerprint(normalized(served))


# ---------------------------------------------------------------------------
# The comparison surface
# ---------------------------------------------------------------------------


def test_declared_objects_names_relations_and_rpcs_the_way_the_surface_does(
    served: dict[str, Any],
) -> None:
    assert declared_objects(served) == {
        "notes",
        "tasks",
        "rpc/create_note",
        "rpc/update_task_status",
    }


def test_the_documents_root_path_is_not_an_object(served: dict[str, Any]) -> None:
    """`/` is the document serving itself. Counting it would make every
    comparison against the surface contract report one object nobody declared."""
    assert "/" in served["paths"]
    assert not any(name in {"", "/"} for name in declared_objects(served))


# ---------------------------------------------------------------------------
# ADR 0050: the gate cannot approve its own subject
# ---------------------------------------------------------------------------


def test_the_module_cannot_write_a_contract() -> None:
    """The structural half of "the gate never rewrites".

    Asserted on the source rather than on the public names, because a writer
    reachable from a public function is a writer whether or not it is exported.
    Goes red if `open(..., "w")`, `write_text`, `write_bytes` or `os.replace`
    ever appears here -- at which point the check path could approve the thing
    it is checking.
    """
    source = Path(openapi_normalize.__file__).read_text(encoding="utf-8")
    body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for writer in ("write_text", "write_bytes", "os.replace", "mkstemp", "shutil.copy"):
        assert writer not in body, f"openapi_normalize reaches a writer: {writer}"
    assert "open(" not in body.replace("load_document", "")
