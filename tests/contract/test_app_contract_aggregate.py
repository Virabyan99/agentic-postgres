"""The aggregate application reference (ADR 0112).

**Nothing asserted this before Run 9, and that is why the storage half was
wrong.** `bin/app-contract.sh --check` compares the committed snapshot byte for
byte, which catches drift and says nothing about whether the document is right;
the gate ran it every session and the storage operations published `200` for a
201 and a 204, no failure responses at all, and a `422` in a shape the service
never emits.

So what is asserted here is not "the snapshot matches" -- the command already
does that -- but that the document **describes the surface**: that both halves
are in it, that the storage half sits under the derived prefix, that every
status published is one the code can produce, and that no schema is published
which nothing references.
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, naming

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMMAND_PATH = REPO_ROOT / "bin" / "app-contract.py"


@pytest.fixture(scope="module")
def command() -> Any:
    specification = importlib.util.spec_from_file_location("apg_app_contract", COMMAND_PATH)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def document(command: Any) -> dict[str, Any]:
    return json.loads(command.generate())


# ---------------------------------------------------------------------------
# It is an aggregate
# ---------------------------------------------------------------------------


def test_both_halves_of_the_surface_are_in_one_document(document: dict[str, Any]) -> None:
    """A visitor sees one API, so the reference is one document (ADR 0112).

    Until Run 9 this captured the auth half alone, which is why nothing had ever
    looked at what the storage half published.
    """
    paths = set(document["paths"])
    assert "/auth/login" in paths, "the auth half is missing from the aggregate"
    assert any(path.startswith(naming.STORAGE_PATH_SUFFIX) for path in paths), (
        "the storage half is missing from the aggregate"
    )


def test_the_storage_half_sits_under_the_derived_prefix(document: dict[str, Any]) -> None:
    """Read from `naming`, never spelled.

    The same constant builds the router's rule, its strip-prefix middleware and
    the published route. A literal here would be a second derivation of a
    published route -- D177, where the documentation route was derived twice, the
    two disagreed, and the copy whose comment said it was kept in step was the
    one that had not drifted.
    """
    expected = {
        f"{naming.STORAGE_PATH_SUFFIX}/upload-intents",
        f"{naming.STORAGE_PATH_SUFFIX}/upload-intents/{{object_id}}/complete",
        f"{naming.STORAGE_PATH_SUFFIX}/objects/{{object_id}}/download-url",
        f"{naming.STORAGE_PATH_SUFFIX}/objects/{{object_id}}",
    }
    assert expected <= set(document["paths"]), (
        f"missing: {sorted(expected - set(document['paths']))}"
    )


def test_the_aggregate_is_titled_as_the_application_api(document: dict[str, Any]) -> None:
    """Both applications share a FastAPI title naming only the auth service.

    Right for each container and wrong for the document a visitor reads: the
    surface it describes is the application API, of which auth is half.
    """
    assert document["info"]["title"] == "Agentic Postgres application API"


def test_a_schema_defined_differently_by_the_two_halves_is_refused(command: Any) -> None:
    """A silent merge would describe one schema and serve the other.

    Four response schemas appear in both halves today because both import
    `errors.py`, and they are byte-identical -- which this asserts rather than
    trusts. The failure would be invisible in review: the merged document would
    be valid, complete, and wrong about one of the two surfaces, and whichever
    half merged second would win.
    """
    auth = {
        "openapi": "3.1.0",
        "info": {"title": "x"},
        "paths": {"/a": {"get": {}}},
        "components": {"schemas": {"Shared": {"type": "object"}}},
    }
    storage = {
        "openapi": "3.1.0",
        "info": {"title": "x"},
        "paths": {"/b": {"get": {}}},
        "components": {"schemas": {"Shared": {"type": "string"}}},
    }
    with pytest.raises(command.ContractError, match="Shared"):
        command._merge(auth, storage, storage_prefix="/storage")

    # The control: identical schemas of one name merge without complaint, which
    # is the case that actually occurs.
    storage["components"]["schemas"]["Shared"] = {"type": "object"}
    merged = command._merge(auth, storage, storage_prefix="/storage")
    assert merged["components"]["schemas"]["Shared"] == {"type": "object"}


def test_a_path_served_by_both_halves_is_refused(command: Any) -> None:
    """Unreachable today, and asserted because the consequence is silent.

    A collision would mean the edge routes one published path to two containers,
    and the document would describe whichever half merged last.
    """
    auth = {
        "openapi": "3.1.0",
        "info": {},
        "paths": {"/storage/x": {"get": {}}},
        "components": {"schemas": {}},
    }
    storage = {
        "openapi": "3.1.0",
        "info": {},
        "paths": {"/x": {"get": {}}},
        "components": {"schemas": {}},
    }
    with pytest.raises(command.ContractError, match="/storage/x"):
        command._merge(auth, storage, storage_prefix="/storage")


# ---------------------------------------------------------------------------
# It describes the surface
# ---------------------------------------------------------------------------


def test_no_operation_publishes_a_success_code_the_route_does_not_return(
    document: dict[str, Any],
) -> None:
    """The three status codes Run 9 found wrong, asserted as the right ones.

    FastAPI defaults to `200` for a handler returning a bare `Response`, so an
    operation answering 201 or 204 published `200` and nobody had looked.
    """
    expected = {
        (f"{naming.STORAGE_PATH_SUFFIX}/upload-intents", "post"): "201",
        (f"{naming.STORAGE_PATH_SUFFIX}/objects/{{object_id}}", "delete"): "204",
        (f"{naming.STORAGE_PATH_SUFFIX}/objects/{{object_id}}/download-url", "get"): "200",
    }
    for (path, verb), code in expected.items():
        responses = document["paths"][path][verb]["responses"]
        successes = sorted(status for status in responses if status.startswith("2"))
        assert successes == [code], (
            f"{verb.upper()} {path} publishes {successes} where the route returns {code}"
        )


def test_the_storage_operations_publish_their_failures(document: dict[str, Any]) -> None:
    """A reference saying every call succeeds is worse than no reference.

    Each expected set is what the route can actually answer, taken from the
    guard's exception mapping rather than from a wish: 401 and 403 everywhere
    behind authentication, 404 where an ownership filter runs, 409 only where a
    state transition can conflict.
    """
    prefix = naming.STORAGE_PATH_SUFFIX
    expected = {
        (f"{prefix}/upload-intents", "post"): {"400", "401", "403", "422"},
        (f"{prefix}/upload-intents/{{object_id}}/complete", "post"): {
            "400",
            "401",
            "403",
            "404",
            "409",
            "422",
        },
        (f"{prefix}/objects/{{object_id}}/download-url", "get"): {"400", "401", "403", "404"},
        (f"{prefix}/objects/{{object_id}}", "delete"): {"400", "401", "403"},
    }
    for (path, verb), failures in expected.items():
        published = {
            status
            for status in document["paths"][path][verb]["responses"]
            if not status.startswith("2")
        }
        assert published == failures, (
            f"{verb.upper()} {path} publishes failures {sorted(published)}, expected "
            f"{sorted(failures)}"
        )


def test_no_operation_publishes_fastapis_validation_error(document: dict[str, Any]) -> None:
    """The service never emits it, so publishing it is ADR 0060's complaint.

    FastAPI adds a `422` to every operation with a parameter. The storage routes
    take one `str` path parameter, which accepts every string, so its validation
    layer rejects nothing -- and a malformed object id is refused by the route
    itself as **400** in the house shape.
    """
    body = json.dumps(document)
    assert "HTTPValidationError" not in body, (
        "the aggregate publishes FastAPI's HTTPValidationError, which this service never returns"
    )
    assert "ValidationError" not in body


def test_every_published_schema_is_referenced(document: dict[str, Any]) -> None:
    """The prune runs to a fixed point, or it leaves an orphan.

    `HTTPValidationError` REFERENCES `ValidationError`, so a single pass computed
    against one snapshot removes the first and finds the second still referenced
    -- by the schema it has just deleted. The first version of the prune did
    exactly that.
    """
    body = json.dumps(document)
    for name in document.get("components", {}).get("schemas", {}):
        assert f'"#/components/schemas/{name}"' in body, (
            f"{name} is published and referenced by nothing"
        )


def test_the_committed_snapshot_is_what_this_checkout_generates(command: Any) -> None:
    """The same comparison `--check` makes, so a drift is a test failure too.

    The gate runs the command; this means a developer running the suite finds
    out before the gate does.
    """
    assert command.SNAPSHOT_PATH.is_file(), f"no snapshot at {command.SNAPSHOT_PATH}"
    assert command.SNAPSHOT_PATH.read_bytes() == command.generate(), (
        "the committed reference disagrees with this checkout. Re-capture with "
        "`bin/app-contract.sh --update`, read the diff, and commit it"
    )


def test_the_snapshot_is_named_for_what_it_holds(command: Any) -> None:
    """It stopped being the auth document in Run 9 and was renamed with it.

    A reviewed artefact whose name describes something else is the kind of stale
    label this repository keeps finding attached to a value nobody re-read.
    """
    assert command.SNAPSHOT_PATH.name == "app-openapi.canonical.json"
