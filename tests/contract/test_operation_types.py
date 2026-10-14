"""The operation types and the refusal of every route that would record one.

CTL-OPS-001 (ADR 0254, D2054): the type table is closed -- exactly the eleven
types stage plan D1953 names, each mapped to a Reality Ledger row, and exactly
the list the control set's `control_operations.type` CHECK carries. The ledger
half (accepted iff available, beta or trial) is the guard in
`test_reality_ledger.py`.

Session 38 (ADR 0256, ADR 0261, D2154): exactly the six executed types are
accepted -- their rows `trial` -- and the five others stay refused; a type not
accepted is refused `409 not_available` naming its row before its body is read,
on every write route; the argument schema the reconciler reads has one branch
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
from app import operations as service_operations

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


#: The six types Session 38 accepts, their rows `trial` since its Run 10 (ADR
#: 0261, D2170) -- written out, never derived from `EXECUTED_TYPES`: building a
#: type is not the decision to accept it.
THE_ACCEPTED_SIX = {
    "project.create",
    "project.delete",
    "project.sleep",
    "project.wake",
    "project.resize",
    "project.export",
}

#: What the reconciler executes since Session 39's Run 6: the six and
#: `credential.rotate` (ADR 0269), which no ledger row accepts before Run 9.
THE_EXECUTED_SEVEN = THE_ACCEPTED_SIX | {"credential.rotate"}

#: Since Session 40 (ADR 0271): the seven and the four branch types, which no
#: ledger row accepts before Run 8.
THE_EXECUTED_ELEVEN = THE_EXECUTED_SEVEN | {
    "branch.create",
    "branch.reset",
    "branch.delete",
    "restore.create",
}


def test_exactly_the_eleven_executed_types_are_accepted() -> None:
    """The exact-set form at Session 40's bump (ADR 0261 authorises it; renamed
    from `test_no_type_is_accepted_and_the_eleven_are_executed`, D1119): every
    type in the table is built and executed, and every one is accepted -- the
    seven's rows re-trialed on a new slot (D2442), the four branch types'
    trialed (ADR 0271) -- and a type outside the table is never accepted. The
    ledger half (accepted iff the row is reachable) is `test_reality_ledger`'s."""
    assert operations.ACCEPTED_TYPES == THE_ELEVEN
    assert operations.EXECUTED_TYPES == THE_EXECUTED_ELEVEN == THE_ELEVEN
    assert THE_EXECUTED_SEVEN < THE_ELEVEN
    assert all(service_operations.is_accepted(t) for t in THE_ELEVEN)
    assert not service_operations.is_accepted("project.rename")


# ---------------------------------------------------------------------------
# Session 38: a type not accepted is refused, and the argument schema
# ---------------------------------------------------------------------------

OPERATIONS_TEMPLATE = (
    REPO_ROOT / "projects" / "control" / "migrations" / "templates" / "0004-control-operations.sql"
)
TEMPLATES = REPO_ROOT / "projects" / "control" / "migrations" / "templates"


def _newest_request_operation() -> str:
    """The NEWEST template that defines `control_request_operation` -- 0005 since
    Session 39 replaces it -- so the type list read is the one a migrated
    cluster runs, never a superseded one."""
    defining = [
        path
        for path in sorted(TEMPLATES.glob("*.sql"))
        if re.search(r"FUNCTION app\.control_request_operation\(", path.read_text("utf-8"))
    ]
    assert defining, "no template defines control_request_operation"
    return defining[-1].read_text(encoding="utf-8")


#: Each write route -> (method, path) with `{key}` for the project.
WRITES = {
    "project.create": ("POST", "/v1/projects"),
    "project.sleep": ("POST", "/v1/projects/{key}/sleep"),
    "project.wake": ("POST", "/v1/projects/{key}/wake"),
    "project.resize": ("PUT", "/v1/projects/{key}/compute"),
    "project.export": ("POST", "/v1/projects/{key}/export"),
    "project.delete": ("DELETE", "/v1/projects/{key}"),
    "credential.rotate": ("POST", "/v1/projects/{key}/credentials"),
}


@pytest.mark.database
def test_a_type_not_accepted_is_refused_not_available_before_its_body(
    drive: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal path, kept executable now that the six are accepted: each
    write route with ITS type withdrawn from the accepted set (the five others
    left in) answers `409 not_available` naming its ledger row, `no-store`,
    before the project or the body is read, and writes no row -- the owner
    asking. The control, in the same invocation: with the six accepted (for
    the control only -- since Session 38's close the committed set is empty,
    D2170) the same request reaches past the gate -- a malformed creation or resize is the
    body's `400`, a write on a project that does not exist is `404` -- so the
    409 was the gate's and nothing else's. And an unauthenticated caller is
    refused before the type is read."""
    owner = drive.account("ops-gate-owner")
    org = drive.organization(owner, "gate")
    token = drive.token("ops-gate-owner", drive.enable_factor(owner))
    before = drive.cluster.query("SELECT count(*) FROM app.control_operations;")
    for operation_type, (method, path) in WRITES.items():
        url = path.format(key="nosuch-prod")
        body = {"organization_id": org, "x": 1}
        monkeypatch.setattr(
            service_operations, "ACCEPTED_TYPES", THE_EXECUTED_SEVEN - {operation_type}
        )
        refused = drive.call(method, url, token=token, body=body)
        assert (refused.status_code, refused.json()) == (
            409,
            {"error": "not_available", "ledger_row": operations.OPERATION_TYPES[operation_type]},
        ), operation_type
        assert refused.headers["cache-control"] == "no-store"
        monkeypatch.undo()
        monkeypatch.setattr(service_operations, "ACCEPTED_TYPES", THE_EXECUTED_SEVEN)
        passed = drive.call(method, url, token=token, body=body)
        monkeypatch.undo()
        with_body = ("project.create", "project.resize", "credential.rotate")
        expected = 400 if operation_type in with_body else 404
        assert passed.status_code == expected, (operation_type, passed.text)
    assert drive.cluster.query("SELECT count(*) FROM app.control_operations;") == before
    listed = drive.call("GET", f"/v1/operations?organization={org}", token=token)
    assert (listed.status_code, listed.json()) == (200, {"operations": []})
    assert drive.call("POST", "/v1/projects", body={}).status_code == 401


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
    executed = re.search(r"IF p_type NOT IN \((.*?)\)", _newest_request_operation(), re.DOTALL)
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
#: A SCRAM-SHA-256 verifier's exact shape: 4096 iterations, a 16-byte salt,
#: two 32-byte keys, base64 (ADR 0269).
VERIFIER = (
    "SCRAM-SHA-256$4096:c2FsdHNhbHRzYWx0c2FsdA==$"
    "U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmVkS2V5U3RvcmU=:"
    "U2VydmVyS2V5U2VydmVyS2V5U2VydmVyS2V5U2VydmU="
)
GOOD_CREATE = {
    "name": "Shop backend",
    "profile": "small",
    "admin_username": "shop.admin",
    "handoff_sha256": "a" * 64,
}
#: Session 40: a branch's creation, its credentials the branch's own.
GOOD_BRANCH = {"branch": "dev", "app_verifier": VERIFIER, "admin_verifier": VERIFIER}

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
    # Session 39 (ADR 0269, D2330): a role and a SCRAM verifier, never a password.
    ("credential.rotate", {"role": "customer_app", "verifier": VERIFIER}, True),
    ("credential.rotate", {"role": "customer_admin", "verifier": VERIFIER}, True),
    ("credential.rotate", {"role": "customer_app", "verifier": VERIFIER + "\n"}, False),
    ("credential.rotate", {"role": "customer_app", "verifier": "hunter2"}, False),
    ("credential.rotate", {"role": "customer_app", "verifier": "md5" + "0" * 32}, False),
    (
        "credential.rotate",
        {"role": "customer_app", "verifier": VERIFIER.replace("4096", "1")},
        False,
    ),
    ("credential.rotate", {"role": "postgres", "verifier": VERIFIER}, False),
    ("credential.rotate", {"role": "customer_app"}, False),
    ("credential.rotate", {"role": "customer_app", "verifier": VERIFIER, "password": "x"}, False),
    # Session 40 (ADR 0271, ADR 0272): a branch's name, its own two verifiers, a
    # point and an expiry as RFC 3339 instants. Never a password, a path or a key.
    ("branch.create", GOOD_BRANCH, True),
    ("branch.create", {**GOOD_BRANCH, "expires_at": "2026-10-15T08:00:00Z"}, True),
    ("branch.create", {**GOOD_BRANCH, "branch": "main"}, False),
    ("branch.create", {**GOOD_BRANCH, "branch": "dev-1"}, False),
    ("branch.create", {**GOOD_BRANCH, "branch": "dev\n"}, False),
    ("branch.create", {**GOOD_BRANCH, "branch": "abcdefghijklm"}, False),
    ("branch.create", {**GOOD_BRANCH, "app_verifier": "hunter2"}, False),
    ("branch.create", {**GOOD_BRANCH, "expires_at": "2026-10-15 08:00:00+00"}, False),
    ("branch.create", {**GOOD_BRANCH, "target_time": "2026-10-14T08:00:00Z"}, False),
    ("branch.create", {**GOOD_BRANCH, "password": "x"}, False),
    ("branch.create", {k: v for k, v in GOOD_BRANCH.items() if k != "admin_verifier"}, False),
    ("restore.create", {**GOOD_BRANCH, "target_time": "2026-10-14T08:00:00.123456Z"}, True),
    ("restore.create", GOOD_BRANCH, False),
    ("restore.create", {**GOOD_BRANCH, "target_time": "2026-10-14T08:00:00+00:00"}, False),
    ("restore.create", {**GOOD_BRANCH, "target_time": "yesterday"}, False),
    ("branch.reset", GOOD_BRANCH, True),
    ("branch.reset", {**GOOD_BRANCH, "target_time": "2026-10-14T08:00:00Z"}, True),
    ("branch.reset", {**GOOD_BRANCH, "branch": "main"}, False),
    ("branch.delete", {"branch": "dev"}, True),
    ("branch.delete", {"branch": "main"}, False),
    ("branch.delete", {}, False),
    ("branch.delete", {"branch": "dev", "project": "slot3-prod"}, False),
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
        "credential.rotate": models.RotateCredentialRequest,
        "branch.create": models.CreateBranchRequest,
        "restore.create": models.CreateRestoreRequest,
        "branch.reset": models.ResetBranchRequest,
    }.get(operation_type)
    if operation_type in ("branch.reset", "branch.delete"):
        # The branch of a reset and of a deletion is the route's PATH, judged by
        # the same pattern the path's handler reaches through the service.
        body = {k: v for k, v in arguments.items() if k != "branch"}
        name = arguments.get("branch")
        path_ok = (
            isinstance(name, str)
            and bool(re.fullmatch(models.BRANCH_PATTERN.strip("^$"), name))
            and name != "main"
        )
        if operation_type == "branch.delete":
            by_model = path_ok and body == {}
        else:
            try:
                models.ResetBranchRequest(**body)
                by_model = path_ok
            except pydantic.ValidationError:
                by_model = False
    elif model is None:
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
