"""The operation types and the refusal of the one route that would create one.

CTL-OPS-001 (ADR 0254, D2054): the type table is closed -- exactly the eleven
types stage plan D1953 names, each mapped to a Reality Ledger row, and exactly
the list the control set's `control_operations.type` CHECK carries -- and
`POST /v1/projects` answers `409 not_available` naming `projects_self_service`
and writes no row. The ledger half (accepted iff available or beta) is the
guard in `test_reality_ledger.py`.
"""

from __future__ import annotations

import re
from typing import Any

import control_cluster as cc
import pytest

from agentic_postgres import REPO_ROOT, operations

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
