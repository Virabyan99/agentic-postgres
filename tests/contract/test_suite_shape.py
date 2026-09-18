"""The suite's own shape: a local may not shadow a module-level helper.

D1509 cost a claim. A test bound a local with the name of a module-level
function, and from that line on the function was unreachable inside that
test -- invisible to an offline suite, because the proof that would have
called it only runs live.

**A pytest fixture is not this class.** A fixture is reached by declaring it as
a parameter, never by calling its name, so a local of the same name in a test
that does not declare it collides with nothing. Measured on 2026-09-18: 50 raw
collisions across `tests/`, of which **45 were fixtures** and 5 were plain
helpers. A guard that reported all 50 would need a 45-entry exemption list
nobody could keep green -- so the discriminator is a property of the
definition, not of the instance that failed (CLAUDE.md §7 rule 5).

The scan carries both controls, because a scan that looks in the wrong place
reports a clean tree in exactly the words a clean tree uses (D374).
"""

from __future__ import annotations

import ast

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

TESTS = REPO_ROOT / "tests"


def _is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr == "fixture":
            return True
        if isinstance(target, ast.Name) and target.id == "fixture":
            return True
    return False


def module_level_helpers(tree: ast.Module) -> set[str]:
    """Module-level functions that are NOT fixtures.

    Imports are deliberately out of scope here: a local named `json` or
    `config` is a different (and much noisier) population, and D1509's class is
    a helper called by name.
    """
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _is_fixture(node)
    }


def shadows(source: str, label: str) -> list[str]:
    """`label:line function shadows name` for every local binding that hides a
    module-level helper. The function's own parameters are excluded: a
    parameter carrying a fixture's name is how a fixture is requested."""
    tree = ast.parse(source)
    helpers = module_level_helpers(tree)
    if not helpers:
        return []

    found: list[str] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = {
            argument.arg
            for group in (
                function.args.posonlyargs,
                function.args.args,
                function.args.kwonlyargs,
            )
            for argument in group
        }
        for extra in (function.args.vararg, function.args.kwarg):
            if extra is not None:
                parameters.add(extra.arg)

        for node in ast.walk(function):
            target = None
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                target = node
            elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                target = node.target
            if target is None or target.id in parameters or target.id not in helpers:
                continue
            found.append(f"{label}:{target.lineno} {function.name}() shadows {target.id}()")
    return found


def test_no_local_shadows_a_module_level_function() -> None:
    """D1509's class, over the whole suite.

    Goes red the next time somebody writes `refused = api_call(...)` over a
    `def refused`. Five such bindings existed on 2026-09-18 and all five were
    repaired in Session 30 Run 5, which is why there is no exemption list here:
    an empty rule is one nobody has to maintain.
    """
    modules = sorted(TESTS.rglob("*.py"))
    assert len(modules) > 100, f"the scan is looking at {len(modules)} modules; it should be ~200"

    problems: list[str] = []
    for path in modules:
        problems.extend(shadows(path.read_text(encoding="utf-8"), str(path.relative_to(REPO_ROOT))))

    assert not problems, (
        "a local hides a module-level helper; from that line the helper is "
        "unreachable inside that function (D1509):\n" + "\n".join(problems)
    )


def test_the_shadow_scan_catches_a_synthetic_shadow() -> None:
    """Anti-vacuity: a module the scan MUST flag, at the BINDING.

    The line is asserted, not merely the count. `assert refused` on the next
    line is a *use* of the same name, so a scan that read `Load` context
    instead of `Store` would still report exactly one finding and this control
    would have passed -- measured, in the Run 5 battery, which is why the line
    is here.
    """
    synthetic = (
        "def refused(result):\n"  # line 1
        "    return bool(result)\n"  # line 2
        "\n"  # 3
        "\n"  # 4
        "def test_thing():\n"  # 5
        "    refused = call()\n"  # 6 -- the binding
        "    assert refused\n"  # 7 -- a use, not a binding
    )
    found = shadows(synthetic, "synthetic.py")
    assert len(found) == 1, f"the scan missed a plain shadow: {found}"
    assert "shadows refused()" in found[0]
    assert found[0].startswith("synthetic.py:6 "), (
        f"the scan flagged a use rather than the binding: {found[0]}"
    )


def test_the_shadow_scan_passes_a_differently_named_local_and_a_fixture() -> None:
    """The other control, and the one that keeps the rule usable.

    Four things that must NOT be flagged: a local with its own name; a local
    carrying a FIXTURE's name; a fixture parameter rebound in the test that
    requested it; and -- the one that matters -- a parameter rebound inside a
    function, where the parameter shares the name of a PLAIN module-level
    helper. Only the last exercises the parameter exclusion: the Run 5 battery
    deleted that exclusion and this control still passed, because every other
    name here is a fixture, which is excluded one step earlier.
    """
    synthetic = (
        "import pytest\n"
        "\n"
        "\n"
        "def refused(result):\n"
        "    return bool(result)\n"
        "\n"
        "\n"
        "def limit():\n"
        "    return 5\n"
        "\n"
        "\n"
        "@pytest.fixture\n"
        "def client():\n"
        "    return 2\n"
        "\n"
        "\n"
        "def helper(limit):\n"
        "    limit = limit or 1\n"
        "    return limit\n"
        "\n"
        "\n"
        "def test_thing(client):\n"
        "    answer = refused(1)\n"
        "    client = client or 3\n"
        "    assert answer and client\n"
    )
    assert shadows(synthetic, "synthetic.py") == []
