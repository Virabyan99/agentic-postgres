"""The connector repository names migration 0036's functions and formats no statement.

`test_workflow_repository.py`'s rules, for the eight connector calls and the one
event-wait park (D1680: a grant ships with its caller). No database is reached
here; 0036's behaviour is `test_connectivity_substrate.py`'s under a real
cluster. This is a scan over the two modules' sources and a drive of the
methods against a fake pool.
"""

from __future__ import annotations

import ast
import re
from typing import Any
from uuid import uuid4

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

APP = REPO_ROOT / "services" / "auth-api" / "app"
MODULE = APP / "connector_repository.py"
WORKFLOWS = APP / "workflow_repository.py"
TEMPLATE = REPO_ROOT / "migrations" / "templates" / "0036-connectivity.sql"

#: Granted to nobody by 0036, so no module the auth service runs may reach them.
NOBODY = (
    "emit_event",
    "connector_install",
    "connector_rehearse_delivery",
    "connector_scopes_match",
)


def _granted() -> set[str]:
    text = TEMPLATE.read_text(encoding="utf-8")
    names: set[str] = set()
    for statement in re.findall(r"GRANT EXECUTE ON FUNCTION\s+(.*?);", text, re.DOTALL):
        if "auth_service" in statement:
            names.update(re.findall(r"app_private\.(\w+)\s*\(", statement))
    return names


def _called(path: Any) -> set[str]:
    source = path.read_text(encoding="utf-8")
    found = set(re.findall(r"SELECT[^\"']*app_private\.(\w+)\s*\(", source))
    found.update(re.findall(r"FROM app_private\.(\w+)\s*\(", source))
    return found


def _statements(path: Any) -> str:
    """The module without its prose: a docstring may NAME a function it must not call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return "\n".join(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "SELECT" in node.value
    )


def test_every_function_0036_grants_is_called_by_a_named_repository() -> None:
    """Eight here, and the event wait's park on the workflow repository beside `park`."""
    granted = _granted()
    assert len(granted) == 9, sorted(granted)
    here = _called(MODULE)
    assert granted - {"workflow_await_event"} <= here, sorted(granted - here)
    assert "workflow_await_event" in _called(WORKFLOWS)
    assert "workflow_await_event" not in here


def test_no_function_granted_to_nobody_is_reachable() -> None:
    """The emitter, the installer, the rehearsal and the scope rule (ADR 0235-0238)."""
    for path in (MODULE, WORKFLOWS):
        statements = _statements(path)
        for name in NOBODY:
            assert name not in statements, f"{path.name} reaches {name}, granted to nobody"


def test_the_connector_repository_formats_no_statement() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            offenders.append(f"an f-string at line {node.lineno}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            offenders.append(f"a %-format at line {node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "format":
                offenders.append(f"a .format() at line {node.lineno}")
    assert not offenders, offenders


def test_every_statement_passes_a_placeholder_for_every_argument() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    declared: dict[str, int] = {}
    for match in re.finditer(r"CREATE FUNCTION app_private\.(\w+)\(([^)]*)\)", template):
        arguments = match.group(2).strip()
        declared[match.group(1)] = 0 if not arguments else len(arguments.split(","))
    assert declared["connector_finish_delivery"] == 5, declared
    assert declared["connector_fire_due"] == 0, declared

    checked = 0
    for path in (MODULE, WORKFLOWS):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"app_private\.(\w+)\(([^)]*)\)", source):
            name = match.group(1)
            if name not in declared:
                continue
            checked += 1
            assert match.group(2).count("%s") == declared[name], (path.name, name)
    assert checked >= 9, checked


# ---------------------------------------------------------------------------
# the methods, against a fake pool
# ---------------------------------------------------------------------------


class _Cursor:
    def __init__(self, row: dict[str, Any] | None, log: list[tuple[str, tuple]]) -> None:
        self._row = row
        self._log = log

    async def execute(self, statement: str, parameters: tuple) -> None:
        self._log.append((statement, parameters))

    async def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Connection:
    def __init__(self, row: dict[str, Any] | None, log: list[tuple[str, tuple]]) -> None:
        self._row = row
        self._log = log

    def cursor(self, row_factory: Any = None) -> _Cursor:
        return _Cursor(self._row, self._log)

    async def __aenter__(self) -> _Connection:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False


class _Pool:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row
        self.log: list[tuple[str, tuple]] = []

    def connection(self) -> _Connection:
        return _Connection(self.row, self.log)


def _repository(row: dict[str, Any] | None = None) -> tuple[Any, _Pool]:
    from app.connector_repository import ConnectorRepository

    pool = _Pool(row)
    return ConnectorRepository(pool), pool


def test_a_claim_with_nothing_to_send_is_none() -> None:
    import asyncio

    repository, pool = _repository(None)
    assert asyncio.run(repository.claim_delivery(holder="h", lease_seconds=30)) is None
    assert pool.log == [("SELECT * FROM app_private.connector_claim_delivery(%s, %s)", ("h", 30))]


def test_a_claim_maps_the_functions_columns_onto_the_dataclass() -> None:
    import asyncio
    from datetime import UTC, datetime

    row = {
        "delivery_id": uuid4(),
        "connector_name": "note-embedded",
        "endpoint": None,
        "rehearsal": True,
        "event_id": uuid4(),
        "event_name": "apg.rehearsal",
        "event_version": 1,
        "emitted_at": datetime.now(UTC),
        "payload": {"rehearsal": True},
        "attempt": 1,
        "max_attempts": 3,
    }
    repository, _ = _repository(row)
    claimed = asyncio.run(repository.claim_delivery(holder="h", lease_seconds=30))
    assert claimed is not None
    assert (claimed.delivery_id, claimed.endpoint, claimed.rehearsal) == (
        row["delivery_id"],
        None,
        True,
    )
    assert (claimed.attempt, claimed.max_attempts, claimed.payload) == (1, 3, {"rehearsal": True})


def test_accept_passes_the_body_as_canonical_json() -> None:
    import asyncio

    run = uuid4()
    repository, pool = _repository({"run_id": str(run)})
    delivery = uuid4()
    got = asyncio.run(
        repository.accept(name="notes-inbox", delivery_id=delivery, body={"b": 1, "a": 2})
    )
    assert got == run
    statement, parameters = pool.log[0]
    assert statement == "SELECT app_private.connector_accept(%s, %s, %s::jsonb) AS run_id"
    assert parameters == ("notes-inbox", delivery, '{"a":2,"b":1}')
