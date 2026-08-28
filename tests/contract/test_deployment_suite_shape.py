"""Properties of the deployment suite itself, asserted offline.

The deployment suite runs only on a host, and a defect in one of its proofs is
therefore invisible until a trip — which is the single most expensive open item
in this repository: *nothing knows which proofs have never executed*, and five
defective never-executed proofs were found across two trips before this file
existed.

This file is the cheap half of the answer. It cannot say whether an assertion is
*true*, but it can say whether a proof would survive being started.
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

DEPLOYMENT = REPO_ROOT / "tests" / "deployment"


def _command_module_fixtures() -> set[str]:
    """Every fixture whose body returns ``_load_command(...)``.

    Derived from the conftest rather than listed here, for D674's reason: a
    hand-typed roster is a second definition, and the second one is always the
    one that goes stale. A fixture added later is covered without anybody
    remembering to add it.
    """
    tree = ast.parse((DEPLOYMENT / "conftest.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Return)
                and isinstance(inner.value, ast.Call)
                and isinstance(inner.value.func, ast.Name)
                and inner.value.func.id == "_load_command"
            ):
                found.add(node.name)
    return found


def test_the_roster_of_command_module_fixtures_is_not_empty() -> None:
    """The control, and it is not optional.

    `_command_module_fixtures` is a scan, and a scan that matches nothing
    reports every file clean forever (D374). If `_load_command` is renamed, this
    goes red here rather than silently retiring the guard below.
    """
    roster = _command_module_fixtures()
    assert "dev_token" in roster and "docs_command" in roster, (
        f"the scan found {sorted(roster)}, which does not include the two fixtures "
        "known to be command modules — it is no longer looking at the right thing"
    )


def test_no_deployment_proof_calls_a_command_module_fixture() -> None:
    """D676. A fixture that returns a *module* is not callable.

    `test_a_rotated_signing_key_is_the_only_one_the_plane_accepts` shipped in
    Session 5 doing `dev_token(project_a, role)`. The fixture returns
    `bin/dev-token.py` loaded as a module; every other caller reaches through it
    as `dev_token.mint(...)`. Measured: `TypeError: 'module' object is not
    callable`.

    **It sat green for five sessions because it has never executed.**
    `APG_ROTATED_JWT_FROM_FILE` is set only inside a rotation window, and no
    window had been run. Found at the terminal instead of here, it would have
    ERRORed *after* the signing key was rotated — the irreversible half.

    This asserts what the code *does* rather than which names it mentions
    (D277): the scan looks for a Call whose func is a Name that is one of the
    test's own parameters. `fixture.attribute(...)` is the correct shape and is
    not matched.
    """
    roster = _command_module_fixtures()
    offences: list[str] = []

    for path in sorted(DEPLOYMENT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            params = {a.arg for a in node.args.args} & roster
            if not params:
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id in params
                ):
                    offences.append(
                        f"{path.relative_to(REPO_ROOT)}:{inner.lineno} "
                        f"{node.name} calls {inner.func.id}(...)"
                    )

    assert not offences, (
        "these proofs call a fixture that returns a module, and every one of them will "
        "raise TypeError the first time it runs — on a host, mid-trip, possibly after an "
        "irreversible step:\n  " + "\n  ".join(offences)
    )
