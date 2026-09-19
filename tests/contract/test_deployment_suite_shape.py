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


# ---------------------------------------------------------------------------
# Every proof belongs to a requirement (D1542)
# ---------------------------------------------------------------------------

#: Deployment proofs that are node ids of no registry entry, each with the
#: session that owes it a requirement. Compared for EQUALITY, not containment:
#: a proof deleted from the tree has to leave this tuple too, and a proof added
#: without a requirement cannot hide in it.
#:
#: Measured in Session 30 Run 2 (rig 30c). The plan expected one -- the Studio
#: orphan -- and found twenty-three, several of them security proofs. They are
#: frozen here rather than registered in a hurry: a requirement written to make
#: a list shorter is a requirement nobody reviewed. Session 31 owns the triage
#: (D1542, and the stage plan's open items).
KNOWN_UNREGISTERED: tuple[str, ...] = (
    # --- Two, after Session 31 Run 5's triage (D1597) ------------------------
    #
    # Twenty of the twenty-two became node ids of a requirement that ALREADY
    # stated their property -- which is what the count was really measuring:
    # not twenty-two unstated properties, but twenty-two proofs nothing had
    # connected to the requirement they were written for. Ten of those
    # requirements gained a sentence; three named the property already and the
    # node id joined in silence.
    #
    # **These two are different and are the reason the triage was worth
    # taking.** ADR 0136's category -- that an rpc which WRITES is ineffective
    # over GET, because PostgREST runs a GET in a read-only transaction and
    # `25006` surfaces as 405 -- is stated by no requirement in the file. Both
    # predictions going in were wrong in opposite directions (D490):
    # volatility protects nothing, and it is the transaction that refuses. A
    # property measured that carefully and registered nowhere is exactly what
    # `test_every_deployment_proof_is_a_node_id_of_some_requirement` exists to
    # surface.
    #
    # They need a NEW entry, and a new entry carries `target_session: 31`,
    # which the registry cannot hold until Run 6 moves `CURRENT_SESSION`
    # (D690). **Run 6 registers them and empties this tuple.**
    "tests/deployment/test_session9_agent_writes.py::test_a_get_against_the_deployed_audit_rpc_is_refused",
    "tests/deployment/test_session9_agent_writes.py::test_the_get_that_was_refused_wrote_nothing",
)


def _registered_node_ids() -> set[str]:
    import re

    import yaml

    registry = yaml.safe_load(
        (REPO_ROOT / "tests" / "acceptance-registry.yaml").read_text(encoding="utf-8")
    )
    return {
        re.sub(r"\[.*\]$", "", node_id)
        for entry in registry
        for node_id in (entry.get("test_nodeids") or [])
    }


def deployment_proofs() -> set[str]:
    """Every `test_` function under `tests/deployment/`, by AST.

    Parsed rather than collected, so a decorator, a `parametrize` or a skip
    mark cannot hide one -- and so this runs without a host.
    """
    found: set[str] = set()
    for path in sorted(DEPLOYMENT.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                found.add(f"tests/deployment/{path.name}::{node.name}")
    return found


def test_every_deployment_proof_is_a_node_id_of_some_requirement() -> None:
    """The direction nothing checked (D1542).

    A proof that belongs to no requirement contributes to no claim, so it can
    error at setup forever while every claim over it reads `passed`. That is
    not hypothetical: it is what `studio_*` did (D1236).
    """
    proofs = deployment_proofs()
    assert len(proofs) > 200, f"the scan found {len(proofs)} proofs; it should be ~260"

    orphans = proofs - _registered_node_ids()
    unexpected = sorted(orphans - set(KNOWN_UNREGISTERED))
    assert not unexpected, (
        "these deployment proofs are node ids of no requirement, so no claim "
        "reads them and nothing would notice if they never ran:\n" + "\n".join(unexpected)
    )

    # Equality, not containment: a proof that was registered or deleted must
    # leave the tuple, or the tuple becomes a list nobody maintains.
    stale = sorted(set(KNOWN_UNREGISTERED) - orphans)
    assert not stale, (
        "KNOWN_UNREGISTERED names proofs that are no longer orphans; remove them:\n"
        + "\n".join(stale)
    )


def test_the_registration_scan_catches_a_synthetic_orphan(tmp_path) -> None:
    """Anti-vacuity (D374): the scan must find a test nothing registers.

    Without this, a scan that walked the wrong directory would report a fully
    registered suite in exactly the words a registered suite uses.
    """
    module = tmp_path / "test_synthetic_orphan.py"
    module.write_text("def test_nobody_registered_this() -> None:\n    assert True\n", "utf-8")

    tree = ast.parse(module.read_text(encoding="utf-8"))
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    assert names == ["test_nobody_registered_this"]
    assert f"tests/deployment/{module.name}::{names[0]}" not in _registered_node_ids()
