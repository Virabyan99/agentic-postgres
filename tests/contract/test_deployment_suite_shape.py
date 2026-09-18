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
    # --- Session 31 owes these twenty-two a requirement each -----------------
    "tests/deployment/test_session11_operations.py::test_a_malformed_request_id_header_does_not_destroy_the_write",
    "tests/deployment/test_session12_isolation_matrix.py::test_the_classifier_can_tell_the_categories_apart",
    "tests/deployment/test_session14_observability.py::test_the_deployed_document_reports_the_metrics_route_it_observed",
    "tests/deployment/test_session20_tenant.py::test_alpha_declares_no_set_and_holds_none_of_betas_objects",
    "tests/deployment/test_session2_edge.py::test_the_deployed_document_agrees_with_the_live_route",
    "tests/deployment/test_session2_edge.py::test_hsts_is_present_on_the_https_response",
    "tests/deployment/test_session2_edge.py::test_the_acme_state_file_matches_the_recorded_environment",
    "tests/deployment/test_session2_edge.py::test_the_health_route_is_reachable_only_through_the_edge",
    "tests/deployment/test_session2_host.py::test_sshd_limits_authentication_attempts",
    "tests/deployment/test_session2_host.py::test_the_edge_publishes_exactly_eighty_and_four_four_three",
    "tests/deployment/test_session2_host.py::test_the_docker_user_chain_is_reachable_from_forward",
    "tests/deployment/test_session2_host.py::test_ufw_denies_incoming_by_default",
    "tests/deployment/test_session2_host.py::test_the_daemon_runs_the_configuration_we_installed",
    "tests/deployment/test_session2_isolation.py::test_the_two_projects_are_actually_distinct",
    "tests/deployment/test_session2_isolation.py::test_an_unknown_hostname_is_not_served",
    "tests/deployment/test_session2_isolation.py::test_the_recorded_networks_are_project_scoped",
    "tests/deployment/test_session2_isolation.py::test_neither_project_joins_the_others_network",
    "tests/deployment/test_session2_isolation.py::test_each_project_holds_only_its_own_secret_generation",
    "tests/deployment/test_session8_agent_plane.py::test_a_read_only_agent_can_neither_discover_nor_invoke_a_write_on_the_deployment",
    "tests/deployment/test_session9_agent_writes.py::test_a_get_against_the_deployed_audit_rpc_is_refused",
    "tests/deployment/test_session9_agent_writes.py::test_the_get_that_was_refused_wrote_nothing",
    "tests/deployment/test_session9_agent_writes.py::test_a_revoked_token_fails_its_next_read_write_and_direct_request",
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
