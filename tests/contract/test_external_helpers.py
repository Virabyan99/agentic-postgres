"""The external suite's pure helpers, proved without a network (D214).

`tests/external/` is collected everywhere and executed only under `-m external`,
which is why D10b requires those modules to be importable with no network at
import time. That makes their pure helpers testable here, and this one needed it:
a case-sensitive header lookup read `None` from a header that was present, and
the only thing that would ever have noticed was an off-host run of the gate.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest
from _pytest._io.saferepr import saferepr

from agentic_postgres import REPO_ROOT, naming

pytestmark = [pytest.mark.contract, pytest.mark.p0]


def _load_external_module():
    """Import the external module by path.

    A bare `from test_session5_public_api import ...` works only from inside
    `tests/external/`, because that is the directory pytest puts on `sys.path`
    for the module it is collecting. Loading by path is what lets a proof in one
    directory measure a helper in another -- and it exercises D10b's rule from
    the outside: an external module must be importable with no network at import
    time, and this import is now a place that would fail if it stopped being.
    """
    path = REPO_ROOT / "tests" / "external" / "test_session5_public_api.py"
    spec = importlib.util.spec_from_file_location("apg_external_public_api", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Headers = _load_external_module().Headers


def test_a_header_is_found_under_any_capitalisation() -> None:
    """RFC 9110 §5.1. Go canonicalises to `Www-Authenticate`; the RFC writes `WWW-`.

    Both spellings are on the wire in this system -- Traefik sends the first and
    the proof asked for the second -- so neither may be privileged.
    """
    headers = Headers([("Www-Authenticate", 'Basic realm="alpha-dev documentation"')])

    for spelling in ("WWW-Authenticate", "Www-Authenticate", "www-authenticate"):
        assert "Basic" in headers.get(spelling, ""), spelling
        assert spelling in headers
        assert headers[spelling].startswith("Basic")


def test_an_absent_header_is_still_absent() -> None:
    """The fix must not make every lookup succeed, which is the way this goes wrong."""
    headers = Headers([("Content-Type", "text/plain")])

    assert headers.get("WWW-Authenticate") is None
    assert headers.get("WWW-Authenticate", "") == ""
    assert "WWW-Authenticate" not in headers
    with pytest.raises(KeyError):
        headers["WWW-Authenticate"]


def test_the_wire_spelling_survives_for_the_failure_message() -> None:
    """Still a dict, because the repr is what made D214 diagnosable in one read."""
    headers = Headers([("Www-Authenticate", "Basic realm=x")])

    assert dict(headers) == {"Www-Authenticate": "Basic realm=x"}
    assert "Www-Authenticate" in repr(headers)


# ---------------------------------------------------------------------------
# D2416 -- a secret an external proof holds is never printed by pytest
# ---------------------------------------------------------------------------

EXTERNAL = REPO_ROOT / "tests" / "external"

#: What a fixture's body (its docstring aside) says when it reads a secret.
SECRET_WORDS = re.compile(r"password|totp|token|credential|secret", re.IGNORECASE)


def _external(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"apg_external_{name}", EXTERNAL / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _printed(value: Any) -> str:
    """What pytest prints for a failing test's or fixture's argument, and repr."""
    return saferepr(value) + repr(value)


def test_a_secret_is_its_value_and_prints_none() -> None:
    """`Secret` is the value to every consumer a proof hands it to -- `==`, an
    f-string, `json`, `str` -- and its `repr`, alone or inside a dict or tuple,
    names none of it, the way pytest prints a failing proof's arguments. The
    control: the same value as a plain `str` in the same containers is printed,
    so the reading can see a value when one is there."""
    Secret = _external("redaction").Secret
    value = "s3cr3t-Value-0123456789"
    secret = Secret(value)
    assert secret == value and f"x{secret}y" == f"x{value}y" and str(secret) == value
    assert json.loads(json.dumps({"password": secret})) == {"password": value}
    for container in (secret, {"customer_app": secret}, ("slot3-prod", {"a": secret}), [secret]):
        assert value not in _printed(container), container
        assert "redacted" in _printed(container)
    for container in (value, {"customer_app": value}, ("slot3-prod", {"a": value})):
        assert value in _printed(container)


def _secret_fixtures(source: str) -> dict[str, bool]:
    """{fixture: whether its body calls `Secret`} for every fixture whose body,
    its docstring aside, names a secret."""
    found = {}
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, ast.FunctionDef) or not any(
            "fixture" in ast.unparse(d) for d in function.decorator_list
        ):
            continue
        body = function.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        text = "\n".join(ast.unparse(statement) for statement in body)
        if SECRET_WORDS.search(text):
            found[function.name] = any(
                isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Secret"
                for statement in body
                for node in ast.walk(statement)
            )
    return found


def test_every_external_fixture_that_reads_a_secret_hands_out_a_secret() -> None:
    """D2416, the class: every fixture under `tests/external/` whose code names
    a password, a TOTP seed, a token, a credential or a secret wraps what it
    returns in `Secret`. Read from the files, so a new fixture is held the day
    it is written. The scan must find the five that exist today; the control:
    a planted fixture that returns a password file's text is an offence, and
    the same fixture wrapping it is not."""
    found = {}
    for path in sorted(EXTERNAL.glob("test_*.py")):
        for name, wrapped in _secret_fixtures(path.read_text("utf-8")).items():
            found[f"{path.name}::{name}"] = wrapped
    assert {
        "test_session37_public_control.py::probe",
        "test_session37_public_control.py::owner",
        "test_session38_public_lifecycle.py::probe",
        "test_session38_public_lifecycle.py::owner",
        "test_session39_public_endpoints.py::slot_creds",
    } <= set(found), sorted(found)
    assert [name for name, wrapped in found.items() if not wrapped] == []
    planted = (
        "@pytest.fixture\ndef creds():\n"
        "    '''Never printed.'''\n    return Path('p').read_text().strip()  # the password\n"
        "@pytest.fixture\ndef holder():\n    return {'password': Path('p').read_text()}\n"
        "@pytest.fixture\ndef kept():\n    return {'password': Secret(Path('p').read_text())}\n"
        "@pytest.fixture\ndef plain():\n    '''No password here.'''\n    return 1\n"
    )
    assert _secret_fixtures(planted) == {"holder": False, "kept": True}


def test_the_secret_fixtures_print_no_value_they_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run-time half: the three fixtures that READ a secret from a file --
    Session 39's `slot_creds` and Sessions 37's and 38's `probe` -- called on
    files written here; what each returns, printed the way pytest prints a
    failing proof's arguments, names no value it read. The control: each value
    is in what the fixture returned, so a proof still gets it."""
    values = {"customer_app": "app-PW-4b1d9e0c", "customer_admin": "adm-PW-77f30a2e"}
    root = tmp_path / "creds"
    (root / "slot3-prod").mkdir(parents=True)
    root.chmod(0o700)
    for role, value in values.items():
        (root / "slot3-prod" / role).write_text(value + "\n", "utf-8")
        (root / "slot3-prod" / role).chmod(0o600)
    monkeypatch.setenv("APG_CUSTOMER_CREDENTIAL_DIR", str(root))
    key, passwords = inspect.unwrap(_external("test_session39_public_endpoints").slot_creds)()
    assert (key, dict(passwords)) == ("slot3-prod", values)
    for value in values.values():
        assert value not in _printed((key, passwords))

    endpoint = "https://control.example.test/api/v1"
    password = tmp_path / "probe-password"
    password.write_text("probe-PW-9c2e41aa\n", "utf-8")
    password.chmod(0o600)
    probe_file = tmp_path / "probe.json"
    probe_file.write_text(json.dumps({
        "endpoint": endpoint, "username": "probe-owner", "password_file": str(password),
        "totp_seed": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    }), "utf-8")  # fmt: skip
    probe_file.chmod(0o600)
    monkeypatch.setenv("APG_CONTROL_PROBE_FILE", str(probe_file))
    for module in ("test_session37_public_control", "test_session38_public_lifecycle"):
        probe = inspect.unwrap(_external(module).probe)(endpoint)
        assert (probe["password"], probe["totp_seed"]) == (
            "probe-PW-9c2e41aa", "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
        ), module  # fmt: skip
        assert "probe-PW-9c2e41aa" not in _printed(probe), module
        assert "JBSWY3DPEHPK3PXP" not in _printed(probe), module
        assert "probe-owner" in _printed(probe), "the reading saw nothing at all"


def _role_keys(source: str) -> list[tuple[int, str]]:
    """Every `NAME["key"]` where NAME was bound to `naming.database_roles(...)`."""
    tree = ast.parse(source)
    bound = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and "database_roles(" in ast.unparse(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    return [
        (node.lineno, node.slice.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in bound
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ]


def test_every_role_a_proof_derives_is_a_role_the_product_derives() -> None:
    """D2416's first failure: `platform["authenticator"]` in a never-executed
    external proof -- `naming` derives `postgrest_authenticator` -- a KeyError
    on first execution. Every string key any external or host proof reads from
    `naming.database_roles(...)` is one the product derives. The scan must find
    the slot proof's three; the control: a planted `authenticator` is found."""
    derived = set(naming.database_roles(naming.sql_key("slot3-prod")))
    offences, read = [], 0
    for path in sorted(
        [*EXTERNAL.glob("test_*.py"), *(EXTERNAL.parent / "deployment").glob("*.py")]
    ):
        for line, key in _role_keys(path.read_text("utf-8")):
            read += 1
            if key not in derived:
                offences.append(f"{path.name}:{line} {key}")
    assert offences == [] and read >= 3, (offences, read)
    planted = 'p = naming.database_roles(k)\nx = [p["app_runtime"], p["authenticator"]]\n'
    assert [key for _, key in _role_keys(planted) if key not in derived] == ["authenticator"]
