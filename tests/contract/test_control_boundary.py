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


# ---------------------------------------------------------------------------
# D2058: the customer proofs reach only the public endpoint
# ---------------------------------------------------------------------------

CUSTOMER_PROOFS = REPO_ROOT / "tests" / "external" / "test_session37_public_control.py"

#: The only environment the customer proofs may read: the control project's
#: document (every URL is its `routes.control`), the probe owner's file, alpha's
#: document (a key's REFUSAL is measured at alpha's routes), and PATH for the
#: product's own commands.
CUSTOMER_ENVIRONMENT = frozenset(
    {"APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_PROJECT_A_OUTPUTS", "PATH"}
)


#: Session 38's customer proofs (D2174): the control project's document, the
#: probe owner's file, the lifecycle's record (the slot's `routes.app` is read
#: from it) and PATH -- alpha's document is not theirs.
LIFECYCLE_PROOFS = REPO_ROOT / "tests" / "external" / "test_session38_public_lifecycle.py"
LIFECYCLE_ENVIRONMENT = frozenset(
    {"APG_CONTROL_OUTPUTS", "APG_CONTROL_PROBE_FILE", "APG_LIFECYCLE_RECORD_FILE", "PATH"}
)


def customer_offences(source: str, allowed: frozenset[str] = CUSTOMER_ENVIRONMENT) -> list[str]:
    """What would let a customer proof reach past the public door: the SSH
    destination or an `ssh`/`scp` word in code, a URL typed rather than read
    from a document, or an environment variable outside `allowed`."""
    import re

    tree = ast.parse(source)
    skipped = _docstrings(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skipped
        ):
            if "APG_SSH_DESTINATION" in node.value:
                found.append("APG_SSH_DESTINATION")
            if re.search(r"(?<![\w-])(ssh|scp)(?![\w-])", node.value, re.IGNORECASE):
                found.append(f"ssh: {node.value[:40]!r}")
            if re.search(r"https?://[A-Za-z0-9\[]", node.value):
                found.append(f"a typed URL: {node.value[:40]!r}")
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "environ"
            and isinstance(node.slice, ast.Constant)
            and node.slice.value not in allowed
        ):
            found.append(f"environment {node.slice.value}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "getenv")
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.startswith(("APG_", "PATH"))
            and node.args[0].value not in allowed
        ):
            found.append(f"environment {node.args[0].value}")
    return found


def test_session37_customer_proofs_reach_only_the_public_endpoint() -> None:
    """D2058. The gate's external mode REQUIRES `--ssh-destination` for Session
    4's proofs, so the customer proofs cannot prove their door by an unset
    variable; they prove it by what they are: no SSH destination, no `ssh` or
    `scp`, no typed URL -- every address is read from a deployed document --
    and no environment but the control project's document, the probe file,
    alpha's document and PATH. The marker names exactly the three it needs.
    The run-time half is the module's own: every request through a recorder
    whose hosts each proof asserts."""
    source = CUSTOMER_PROOFS.read_text(encoding="utf-8")
    assert customer_offences(source) == [], customer_offences(source)
    tree = ast.parse(source)
    markers = [
        sorted(arg.value for arg in node.args if isinstance(arg, ast.Constant))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "requires_environment"
    ]
    assert markers == [sorted(CUSTOMER_ENVIRONMENT - {"PATH"})], markers
    # The control: each kind, planted, is found; the words in a docstring are not.
    planted = {
        "host = os.environ['APG_SSH_DESTINATION']": "APG_SSH_DESTINATION",
        "subprocess.run(['ssh', 'op@host', 'true'])": "ssh",
        "url = 'https://control.example.test/api/v1'": "a typed URL",
        "x = os.environ.get('APG_PROJECT_B_OUTPUTS')": "environment APG_PROJECT_B_OUTPUTS",
    }
    for planted_source, expected in planted.items():
        assert any(expected in hit for hit in customer_offences(planted_source)), planted_source
    assert customer_offences('"""Never ssh, never https://example.test."""') == []


def test_session38_customer_proofs_reach_only_the_public_endpoint() -> None:
    """D2174, D2058's scan extended to Session 38's lifecycle proofs: no SSH
    destination, no `ssh` or `scp`, no typed URL -- every address is the
    control project's `routes.control` or the slot's `routes.app` the
    lifecycle recorded -- and no environment but the control project's
    document, the probe file, the lifecycle record and PATH; the marker names
    exactly the three it needs. The run-time half is the module's own
    recorder. The control: alpha's document, which the Session 37 proofs may
    read, is an offence here -- the allowance is per module, not shared."""
    source = LIFECYCLE_PROOFS.read_text(encoding="utf-8")
    found = customer_offences(source, LIFECYCLE_ENVIRONMENT)
    assert found == [], found
    tree = ast.parse(source)
    markers = [
        sorted(arg.value for arg in node.args if isinstance(arg, ast.Constant))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "requires_environment"
    ]
    assert markers == [sorted(LIFECYCLE_ENVIRONMENT - {"PATH"})], markers
    planted = "x = os.environ['APG_PROJECT_A_OUTPUTS']"
    assert customer_offences(planted) == []
    assert customer_offences(planted, LIFECYCLE_ENVIRONMENT) == [
        "environment APG_PROJECT_A_OUTPUTS"
    ]
    assert customer_offences("x = os.environ['APG_SLOT_OUTPUTS']", LIFECYCLE_ENVIRONMENT) == [
        "environment APG_SLOT_OUTPUTS"
    ]
