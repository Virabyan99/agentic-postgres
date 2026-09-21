"""The repository names migration 0034's functions and formats no statement.

**This module exists because a guard fired** (D1680).
`test_migrations.py::test_every_granted_function_has_a_caller` refuses a `GRANT
EXECUTE` on a function no code calls — *"a grant nobody can audit against a
caller that does not exist"*, 0011's rule, guarded as a class since D837 — and
its docstring names the shape exactly: *"a plane half-built one run early."*
Migration 0034's grants shipped in Run 3 and their callers were planned for Run
5, which is that shape. The caller now ships with the grants, and this module is
what makes it a caller rather than a file.

What it does NOT do: reach a database. The substrate's behaviour is
`test_workflow_substrate.py`'s, under a real cluster as `migration_user`. This
is a scan over the module's source and a drive of its methods against a fake
pool — so a failure here is about the statements this process would send, and
never about what the database does with them.
"""

from __future__ import annotations

import ast
import re
from typing import Any
from uuid import uuid4

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

MODULE = REPO_ROOT / "services" / "auth-api" / "app" / "workflow_repository.py"
TEMPLATE = REPO_ROOT / "migrations" / "templates" / "0034-workflow-substrate.sql"

#: The eight the migration grants to `{{auth_service}}`. Derived from the
#: TEMPLATE below rather than written here, so a grant added later cannot leave
#: this list behind — which is the failure mode of every hand-kept roster in
#: this tree (D816).
GRANTED_TO_THE_SERVICE = "auth_service"


def granted_functions() -> set[str]:
    """Every `app_private` function 0034 grants to the auth service role."""
    text = TEMPLATE.read_text(encoding="utf-8")
    names: set[str] = set()
    for statement in re.findall(r"GRANT EXECUTE ON FUNCTION\s+(.*?);", text, re.DOTALL):
        if GRANTED_TO_THE_SERVICE not in statement:
            continue
        names.update(re.findall(r"app_private\.(\w+)\s*\(", statement))
    return names


def test_every_function_0034_grants_is_called_by_this_module() -> None:
    """The guard's rule, asserted here rather than only in the class scan.

    The class guard reads a haystack of every service, `bin/` and `src/` file at
    once, so it says *somebody* calls it. This says THIS module does, which is
    what makes the grant auditable against a named caller.
    """
    granted = granted_functions()
    assert len(granted) == 8, sorted(granted)

    source = MODULE.read_text(encoding="utf-8")
    called = set(re.findall(r"SELECT[^\"']*app_private\.(\w+)\s*\(", source))
    called.update(re.findall(r"FROM app_private\.(\w+)\s*\(", source))

    missing = sorted(granted - called)
    assert not missing, f"0034 grants {missing} and this repository calls none of them"


def test_the_install_function_is_not_reachable_from_this_module() -> None:
    """The ninth is granted to NOBODY and must not have a method (ADR 0228).

    The deploy calls it as the bootstrap superuser through the container. A
    method here would put a definition-writing authority behind an identity
    reachable over HTTP, which is 0020's reason for keeping a DELETE out of the
    audit reader.
    """
    source = MODULE.read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith(("#", '"', "*", "-"))
    )
    assert "workflow_install_definition" not in body, (
        "the repository reaches the install function, which is granted to nobody"
    )


def test_the_workflow_repository_formats_no_statement() -> None:
    """Every value is a parameter and every statement is a literal.

    An f-string or a `%`-format anywhere near a statement is what this refuses,
    and it is a SCAN rather than a judgement precisely because a scan cannot be
    talked out of it. `storage_repository.py`'s own guard is the precedent.
    """
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
    """The arity of the call and the count of `%s` agree, statement by statement.

    A statement naming a released function with the wrong number of placeholders
    is the defect `test_database_function_signatures` exists for, arriving one
    layer down where that guard's text scan cannot see it: it counts the
    ARGUMENTS in the SQL text, and here they are all `%s`.
    """
    source = MODULE.read_text(encoding="utf-8")
    declared: dict[str, int] = {}
    template = TEMPLATE.read_text(encoding="utf-8")
    for match in re.finditer(r"CREATE FUNCTION app_private\.(\w+)\(([^)]*)\)", template):
        name, arguments = match.group(1), match.group(2).strip()
        declared[name] = 0 if not arguments else len(arguments.split(","))

    for match in re.finditer(r"app_private\.(\w+)\(([^)]*)\)", source):
        name, arguments = match.group(1), match.group(2)
        if name not in declared:
            continue
        placeholders = arguments.count("%s")
        assert placeholders == declared[name], (
            f"{name} is declared with {declared[name]} argument(s) and this module's "
            f"statement passes {placeholders} placeholder(s)"
        )


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
    """Enough of `AsyncConnectionPool` for the repository to be driven."""

    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row
        self.log: list[tuple[str, tuple]] = []

    def connection(self) -> _Connection:
        return _Connection(self.row, self.log)


def _repository(row: dict[str, Any] | None = None) -> tuple[Any, _Pool]:
    from app.workflow_repository import WorkflowRepository

    pool = _Pool(row)
    return WorkflowRepository(pool), pool


def test_a_claim_with_nothing_to_do_is_none_rather_than_an_empty_step() -> None:
    """The loop sleeps on `None`; an empty `ClaimedStep` would be a step it ran.

    D600's shape at the seam that matters most: a value that looks measured and
    is not. A repository that returned a zeroed step would have the loop mint a
    token for agent `00000000-…` and call a tool named `''`.
    """
    import asyncio

    repository, pool = _repository(row=None)
    assert asyncio.run(repository.claim(holder="h", lease_seconds=30)) is None
    assert pool.log[0][1] == ("h", 30)


def test_a_claim_maps_the_functions_spelling_onto_the_dataclass() -> None:
    """`step_position` and `step_name` are the function's names, not the loop's.

    `position` is a `col_name_keyword` and is a syntax error as a bare OUT
    parameter in `RETURNS TABLE` (D1675), so the substrate returns
    `step_position`. This asserts the mapping exists, because a rename that
    reached the dataclass would be an `AttributeError` at the first live claim.
    """
    import asyncio

    run = uuid4()
    step = uuid4()
    agent = uuid4()
    repository, _ = _repository(
        row={
            "step_id": step,
            "run_id": run,
            "step_position": 2,
            "step_name": "second",
            "attempt": 1,
            "agent_id": agent,
            "dry_run": False,
            "step": {"tool": "create_note"},
            "input": {"title": "x"},
            "prior": {"first": {"row": 1}},
            "timeout_seconds": 30,
            "idempotency_key": f"wf-{run}-second",
        }
    )
    claimed = asyncio.run(repository.claim(holder="h", lease_seconds=30))
    assert claimed is not None
    assert claimed.position == 2
    assert claimed.name == "second"
    assert claimed.prior == {"first": {"row": 1}}
    assert claimed.idempotency_key == f"wf-{run}-second"


def test_finish_and_park_return_the_words_the_substrate_returns() -> None:
    """`lease_lost` reaches the caller as itself, and is not an exception.

    The work was done and a successor holds the row; raising here would report a
    failure that did not occur. `storage_finish_cleanup`'s rule, one plane over.
    """
    import asyncio

    repository, pool = _repository(row={"status": "lease_lost"})
    assert (
        asyncio.run(
            repository.finish(
                step_id=uuid4(), holder="h", outcome="succeeded", result=None, reason=None
            )
        )
        == "lease_lost"
    )
    assert pool.log[0][1][2] == "succeeded"

    repository, _ = _repository(row={"outcome": "parked"})
    assert (
        asyncio.run(
            repository.park(step_id=uuid4(), holder="h", reason="write_conflict", resume_after=None)
        )
        == "parked"
    )
