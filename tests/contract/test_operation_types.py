"""The operation types and the refusal of every route that would record one.

CTL-OPS-001 (ADR 0254, D2054): the type table is closed -- exactly the eleven
types stage plan D1953 names, each mapped to a Reality Ledger row, and exactly
the list the control set's `control_operations.type` CHECK carries -- and
`POST /v1/projects` answers `409 not_available` naming `projects_self_service`
and writes no row. The ledger half (accepted iff available or beta) is the
guard in `test_reality_ledger.py`.

Session 38 (ADR 0256, D2154): every write route is refused the same way while
its row is planned; the argument schema the reconciler reads has one branch
per executed type and agrees with the control mode's models on every example.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, get_args

import control_cluster as cc
import pydantic
import pytest
from jsonschema import Draft202012Validator

from agentic_postgres import REPO_ROOT, operations
from app import compute_profiles, errors, models

pytestmark = [pytest.mark.contract, pytest.mark.p0]

#: Stage plan D1953's types, written out here as the closed list the table
#: must equal -- a twelfth type added to the module fails this until it is
#: added here, with its ledger row, on purpose.
THE_ELEVEN = {
    "project.create",
    "project.delete",
    "project.sleep",
    "project.wake",
    "project.resize",
    "project.export",
    "branch.create",
    "branch.reset",
    "branch.delete",
    "restore.create",
    "credential.rotate",
}

REGISTRY_TEMPLATE = (
    REPO_ROOT / "projects" / "control" / "migrations" / "templates" / "0003-control-registry.sql"
)


def _check_list() -> set[str]:
    """The literals of `control_operations.type`'s CHECK, read from the set."""
    text = REGISTRY_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"type\s+text NOT NULL CHECK \(type IN \((.*?)\)\)", text, re.DOTALL)
    assert match is not None, "the operations table's type CHECK was not found"
    return set(re.findall(r"'([a-z_.]+)'", match.group(1)))


def test_the_type_table_is_closed() -> None:
    assert set(operations.OPERATION_TYPES) == THE_ELEVEN
    assert _check_list() == THE_ELEVEN
    assert operations.ACCEPTED_TYPES <= set(operations.OPERATION_TYPES)
    # Every type names a row of the concept it acts on, never an empty string.
    assert all(isinstance(row, str) and row for row in operations.OPERATION_TYPES.values())


@pytest.fixture(scope="module")
def drive(tmp_path_factory: pytest.TempPathFactory) -> Any:
    try:
        with cc.control_cluster() as cluster:
            with cc.control_app(cluster, tmp_path_factory.mktemp("control-ops")) as driver:
                yield driver
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.mark.database
def test_project_creation_is_refused_as_not_available(drive: Any) -> None:
    owner = drive.account("ops-owner")
    org = drive.organization(owner)
    token = drive.token("ops-owner", drive.enable_factor(owner))
    before = drive.cluster.query("SELECT count(*) FROM app.control_operations;")
    refused = drive.call(
        "POST", "/v1/projects", token=token, body={"organization_id": org, "name": "new"}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json() == {"error": "not_available", "ledger_row": "projects_self_service"}
    assert refused.headers["cache-control"] == "no-store"
    assert drive.cluster.query("SELECT count(*) FROM app.control_operations;") == before
    listed = drive.call("GET", f"/v1/operations?organization={org}", token=token)
    assert (listed.status_code, listed.json()) == (200, {"operations": []})
    # Control: an unauthenticated caller is refused before the type is read.
    assert drive.call("POST", "/v1/projects", body={}).status_code == 401


# ---------------------------------------------------------------------------
# Session 38: every write is refused while planned, and the argument schema
# ---------------------------------------------------------------------------

OPERATIONS_TEMPLATE = (
    REPO_ROOT / "projects" / "control" / "migrations" / "templates" / "0004-control-operations.sql"
)

#: Each write route -> (method, path) with `{key}` for the project.
WRITES = {
    "project.sleep": ("POST", "/v1/projects/{key}/sleep"),
    "project.wake": ("POST", "/v1/projects/{key}/wake"),
    "project.resize": ("PUT", "/v1/projects/{key}/compute"),
    "project.export": ("POST", "/v1/projects/{key}/export"),
    "project.delete": ("DELETE", "/v1/projects/{key}"),
}


@pytest.mark.database
def test_every_write_is_refused_as_not_available_while_planned(drive: Any) -> None:
    """While every row is planned (ADR 0254) each write answers `not_available`
    naming its ledger row, before its body is read, and writes no row --
    whoever asks, a member or the owner."""
    assert operations.ACCEPTED_TYPES == frozenset()
    owner = drive.account("ops-writes-owner")
    org = drive.organization(owner, "writes")
    token = drive.token("ops-writes-owner", drive.enable_factor(owner))
    drive.cluster.query(
        f"SELECT app.control_adopt_project('writes-prod', '{org}', 'writes', 'prod', "
        "'writes.test', '1.16.0', 'abc')"
    )
    before = drive.cluster.query("SELECT count(*) FROM app.control_operations;")
    for operation_type, (method, path) in WRITES.items():
        refused = drive.call(method, path.format(key="writes-prod"), token=token, body={"x": 1})
        assert (refused.status_code, refused.json()) == (
            409,
            {"error": "not_available", "ledger_row": operations.OPERATION_TYPES[operation_type]},
        ), operation_type
    assert drive.cluster.query("SELECT count(*) FROM app.control_operations;") == before


def _schema() -> dict[str, Any]:
    return json.loads((REPO_ROOT / operations.ARGUMENT_SCHEMA_PATH).read_text(encoding="utf-8"))


def test_the_argument_schema_has_one_branch_per_executed_type() -> None:
    """D2154: a branch for every type the reconciler executes and no other; a
    type may be accepted only if it is executed; the result members and the
    profile enum are the same lists everywhere they are written."""
    schema = _schema()
    branches = set()
    for branch in schema["oneOf"]:
        branches.add(branch["properties"]["type"]["const"])
    assert branches == operations.EXECUTED_TYPES
    assert operations.EXECUTED_TYPES <= set(operations.OPERATION_TYPES)
    assert operations.ACCEPTED_TYPES <= operations.EXECUTED_TYPES
    assert set(operations.RESULT_MEMBERS) == operations.EXECUTED_TYPES
    assert tuple(schema["$defs"]["profile"]["enum"]) == compute_profiles.PROFILE_NAMES
    assert get_args(models.ComputeProfile) == compute_profiles.PROFILE_NAMES
    sql = OPERATIONS_TEMPLATE.read_text(encoding="utf-8")
    profile_check = re.search(r"profile\s+text NULL CHECK \(profile IN \((.*?)\)\)", sql)
    assert profile_check is not None
    assert tuple(re.findall(r"'([a-z]+)'", profile_check.group(1))) == (
        compute_profiles.PROFILE_NAMES
    )
    executed = re.search(r"IF p_type NOT IN \((.*?)\)", sql, re.DOTALL)
    assert executed is not None
    assert set(re.findall(r"'([a-z_.]+)'", executed.group(1))) == operations.EXECUTED_TYPES


def test_the_error_codes_are_one_closed_list() -> None:
    sql = OPERATIONS_TEMPLATE.read_text(encoding="utf-8")
    check = re.search(r"control_operations_error_code_check CHECK \(error_code IN \((.*?)\)\)", sql,
                      re.DOTALL)  # fmt: skip
    assert check is not None
    assert set(re.findall(r"'([a-z_]+)'", check.group(1))) == errors.OPERATION_ERROR_CODES


#: (type, arguments) -> valid? Each example is judged by the schema the
#: reconciler reads and by the model the control mode reads, and the two must
#: agree on every one (D2154). The trailing-newline cases are why the schema
#: does not end its patterns in `$` (D2199).
GOOD_CREATE = {
    "name": "Shop backend",
    "profile": "small",
    "admin_username": "shop.admin",
    "handoff_sha256": "a" * 64,
}
EXAMPLES: list[tuple[str, dict[str, Any], bool]] = [
    ("project.create", GOOD_CREATE, True),
    ("project.create", {**GOOD_CREATE, "name": "x" * 48}, True),
    ("project.create", {**GOOD_CREATE, "name": "x" * 49}, False),
    ("project.create", {**GOOD_CREATE, "name": ""}, False),
    ("project.create", {**GOOD_CREATE, "name": "shop\n"}, False),
    ("project.create", {**GOOD_CREATE, "name": "shop; rm -rf /"}, False),
    ("project.create", {**GOOD_CREATE, "admin_username": "shop.admin\n"}, False),
    ("project.create", {**GOOD_CREATE, "admin_username": "Shop"}, False),
    ("project.create", {**GOOD_CREATE, "admin_username": "ab"}, False),
    ("project.create", {**GOOD_CREATE, "admin_username": "a" + "b" * 62}, True),
    ("project.create", {**GOOD_CREATE, "admin_username": "a" + "b" * 63}, False),
    ("project.create", {**GOOD_CREATE, "admin_username": "--help"}, False),
    ("project.create", {**GOOD_CREATE, "handoff_sha256": "A" * 64}, False),
    ("project.create", {**GOOD_CREATE, "handoff_sha256": "a" * 64 + "\n"}, False),
    ("project.create", {**GOOD_CREATE, "profile": "huge"}, False),
    ("project.create", {**GOOD_CREATE, "key": "slot1-prod"}, False),
    ("project.create", {k: v for k, v in GOOD_CREATE.items() if k != "admin_username"}, False),
    ("project.resize", {"profile": "large"}, True),
    ("project.resize", {"profile": "large", "command": "x"}, False),
    ("project.resize", {}, False),
    ("project.sleep", {}, True),
    ("project.sleep", {"path": "/etc"}, False),
    ("project.delete", {}, True),
    ("project.export", {"schemas": ["app_private"]}, False),
]


@pytest.mark.parametrize(("operation_type", "arguments", "valid"), EXAMPLES)
def test_the_schema_and_the_models_agree(
    operation_type: str, arguments: dict[str, Any], valid: bool
) -> None:
    validator = Draft202012Validator(_schema(), format_checker=Draft202012Validator.FORMAT_CHECKER)
    by_schema = validator.is_valid({"type": operation_type, "arguments": arguments})
    model = {
        "project.create": models.CreateProjectRequest,
        "project.resize": models.ResizeProjectRequest,
    }.get(operation_type)
    if model is None:
        by_model = arguments == {}
    else:
        body = dict(arguments)
        if operation_type == "project.create":
            body["organization"] = str(uuid.uuid4())
        try:
            model(**body)
            by_model = True
        except pydantic.ValidationError:
            by_model = False
    assert (by_schema, by_model) == (valid, valid), (operation_type, arguments)
