"""The control mode reads nothing of another project (CTL-API-001, ADR 0251).

The control plane's records are its own set's rows; the registry was written
by root from the deployed documents (`bin/control.sh adopt`, Run 6), never
read by the service. So no module the control mode adds may read a deployed
document, an outputs path, the projects' configuration root, a password or a
passfile, or reach anything over HTTP. An AST scan of the code -- docstrings
and comments excluded, so a sentence explaining the rule is not an offence --
over `control_*.py`, `totp.py` and `operations.py`, beside a control proving
the scan sees each kind of offence it looks for.
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.security, pytest.mark.p0]

APP = REPO_ROOT / "services" / "auth-api" / "app"

#: Names whose appearance in code means a read of another project, or a way
#: off the host.
FORBIDDEN_NAMES = frozenset(
    {
        "deployed_output",
        "read_deployed_document",
        "agentic_postgres",
        "httpx",
        "requests",
        "urllib",
        "aiohttp",
        "socket",
        "http",
        "subprocess",
    }
)

#: Text whose appearance in a string literal means the same.
FORBIDDEN_TEXT = ("outputs.json", "/etc/agentic-postgres/projects", "_password", "pgpass")


def _control_modules() -> list[str]:
    names = sorted(
        path.name
        for path in APP.glob("*.py")
        if path.name.startswith("control_") or path.name in ("totp.py", "operations.py")
    )
    return names


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of the string nodes that are docstrings."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def offences(source: str) -> list[str]:
    tree = ast.parse(source)
    skipped = _docstrings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_NAMES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_NAMES:
                found.append(node.module)
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.append(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            found += [text for text in FORBIDDEN_TEXT if text in node.value]
    return found


def test_the_control_mode_reads_no_other_projects_credential() -> None:
    modules = _control_modules()
    assert {
        "control_repository.py",
        "control_roles.py",
        "control_routes.py",
        "control_service.py",
        "totp.py",
        "operations.py",
    } <= set(modules), modules
    found = {
        name: offences((APP / name).read_text(encoding="utf-8"))
        for name in modules
    }  # fmt: skip
    found = {name: hits for name, hits in found.items() if hits}
    assert not found, f"the control mode reaches past its own records: {found}"


def test_the_scan_sees_each_kind_of_offence() -> None:
    """The control: every kind the scan looks for, planted, is found; the same
    words in a docstring are not."""
    planted = {
        "import httpx": "httpx",
        "from agentic_postgres import deployed_output": "agentic_postgres",
        "document = deployed_output.read_deployed_document(key)": "deployed_output",
        "path = '/etc/agentic-postgres/projects/alpha'": "/etc/agentic-postgres/projects",
        "name = 'authenticator_password'": "_password",
        "with open('outputs.json') as handle: pass": "outputs.json",
        "import urllib.request": "urllib.request",
    }
    for source, expected in planted.items():
        assert expected in offences(source), source
    assert offences('"""We never read outputs.json or a pgpass, nor import httpx."""') == []
