"""`bin/workflow.sh init|validate`, driven as an operator drives them.

**The product's own command, not the functions behind it** (D1114). The
compiler has its own module of proofs; what is asked here is whether the two
verbs an operator actually types do what their help says, with the exit codes
the runbook's convention assigns -- including the four verbs this checkout does
not serve, which must say so rather than fail in a way that reads like a typo.

Nothing here reaches a host, a root, a container or a network. That is the
claim `validate` makes about itself and it is checked by making it: the arms
below run in a temporary directory with no rendered document anywhere.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMMAND = REPO_ROOT / "bin" / "workflow.sh"
EXAMPLE = REPO_ROOT / "project.example.yaml"
SECOND = REPO_ROOT / "project.second.example.yaml"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(COMMAND), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_compiles_the_example_projects_definitions() -> None:
    result = run("validate", "--project", str(EXAMPLE))
    assert result.returncode == 0, result.stderr
    assert "notes-roundtrip.yaml" in result.stdout
    assert "notes-retry.yaml" in result.stdout
    assert re.search(r"lock tools_sha256\s+[0-9a-f]{64}", result.stdout), (
        "validate does not report WHAT it compiled against, so a reader cannot "
        "tell whether the lock moved since"
    )


def test_validate_refuses_naming_the_file_the_step_and_the_reason(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text(
        "schema_version: 1\nname: broken\nversion: 1\ndescription: x\n"
        "steps:\n  - name: the_step\n    capability: not_a_capability@1.0.0\n",
        encoding="utf-8",
    )
    result = run("validate", "--project", str(EXAMPLE), "--file", str(path))
    assert result.returncode == 5, result.stdout + result.stderr
    assert "broken.yaml" in result.stderr
    assert "step the_step" in result.stderr
    assert "compiles no capability named" in result.stderr


def test_a_validate_that_is_going_to_refuse_prints_no_success_sentence(
    tmp_path: Path,
) -> None:
    """**D1403.** A sentence already on the terminal cannot be taken back.

    The refusing run must write NOTHING to stdout: the report is held until
    every file has compiled, so `compiles` cannot appear above a refusal. The
    control is `test_validate_compiles_the_example_projects_definitions`, which
    requires the same sentence to still be printed when nothing refuses -- a
    repair that deleted it would satisfy this half by taking a true report
    away.
    """
    broken = tmp_path / "zzz-broken.yaml"
    broken.write_text(
        "schema_version: 1\nname: broken\nversion: 1\ndescription: x\n"
        "steps:\n  - name: s\n    capability: list_resources@1.0.0\n",
        encoding="utf-8",
    )
    result = run("validate", "--project", str(EXAMPLE), "--file", str(broken))
    assert result.returncode == 5
    assert "compile against this project's lock" not in result.stdout, (
        f"validate wrote a success sentence to stdout and then exited "
        f"{result.returncode}:\n{result.stdout}"
    )


def test_a_project_with_no_migration_set_is_reported_as_declaring_none() -> None:
    """Not zero definitions and not an error: a project without a set has no
    workflows/ directory to have definitions IN, and saying `0` would read as
    a directory somebody emptied."""
    result = run("validate", "--project", str(SECOND))
    assert result.returncode == 0, result.stderr
    assert "declares no migrations.set" in result.stdout


def test_validate_needs_no_host_no_root_and_no_render(tmp_path: Path) -> None:
    """Run from a directory that is not the checkout, with no `.generated`
    anywhere in reach. A lock is COMPUTED from the approved contract and the
    project's own, and discarded."""
    result = subprocess.run(
        [str(COMMAND), "validate", "--project", str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir()), "validate wrote something into the working directory"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_prints_a_skeleton_and_writes_no_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(COMMAND), "init", "--project", str(EXAMPLE), "--name", "a-scaffold"],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir()), "init wrote a file; it streams to stdout"

    document = yaml.safe_load(result.stdout)
    assert document["name"] == "a-scaffold"
    assert document["schema_version"] == 1
    assert document["steps"], "a skeleton with no steps teaches nothing"


def test_the_skeleton_names_only_capabilities_the_lock_really_serves() -> None:
    """**The whole point of deriving it from the lock** (the `agent.sh init`
    shape): a scaffold that named a capability the compiler refuses would be a
    scaffold whose first edit is a deletion."""
    from agentic_postgres import workflow_definition as wd

    lock = wd.lock_view_for_project(EXAMPLE)
    served = set(lock.capability_names)

    result = run("init", "--project", str(EXAMPLE))
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load(result.stdout)
    named = {step["capability"] for step in document["steps"]}
    assert named <= served, f"the skeleton names {sorted(named - served)}, which the lock has not"


def test_the_skeleton_never_names_a_capability_that_requires_approval() -> None:
    """`set_note_embedding@1.0.0` is `requires_approval: true`, so a step
    naming it compiles only with an `approval:` block and runs only when a
    human decides. The skeleton is the smallest definition that validates, and
    that is not it."""
    result = run("init", "--project", str(EXAMPLE))
    document = yaml.safe_load(result.stdout)
    assert "set_note_embedding@1.0.0" not in {step["capability"] for step in document["steps"]}


def test_the_skeleton_validates_once_its_placeholders_are_filled(tmp_path: Path) -> None:
    """**The round trip, and it is the strongest thing this module asserts.**

    `init` is only useful if what it prints compiles. The only edits made here
    are the ones its own comments ask for -- the description and the `TODO`
    argument values -- so a skeleton that needed a structural change to compile
    fails this.
    """
    result = run("init", "--project", str(EXAMPLE), "--name", "round-trip")
    assert result.returncode == 0, result.stderr

    filled = result.stdout.replace(": TODO\n", ": a value\n")
    filled = re.sub(r"(?m)^description: >-\n(  .*\n)+", "description: a filled skeleton\n", filled)
    path = tmp_path / "round-trip.yaml"
    path.write_text(filled, encoding="utf-8")

    validated = run("validate", "--project", str(EXAMPLE), "--file", str(path))
    assert validated.returncode == 0, (
        f"the skeleton `init` prints does not compile:\n{validated.stderr}\n\n{filled}"
    )


def test_a_definition_name_the_column_would_refuse_is_refused_here() -> None:
    result = run("init", "--project", str(EXAMPLE), "--name", "Not_A_Name")
    assert result.returncode == 2
    assert "is not a definition name" in result.stderr


# ---------------------------------------------------------------------------
# The four that reach a deployment
# ---------------------------------------------------------------------------


@pytest.fixture
def outputs(tmp_path: Path) -> Path:
    """A rendered outputs document naming an address nothing answers on.

    Nothing here dials anything: every arm below asserts what the command
    BUILDS -- which route, which method, which body -- and the one arm that
    does reach a socket asserts the refusal, which is exit 3 and a sentence.
    """
    path = tmp_path / "outputs.json"
    path.write_text(
        json.dumps({"routes": {"app": {"url": "http://127.0.0.1:9/app", "status": "ready"}}}),
        encoding="utf-8",
    )
    return path


def workflow_module() -> Any:
    """`bin/workflow.py`, loaded by path -- it is a command, not a package."""
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "apg_workflow_command", REPO_ROOT / "bin" / "workflow.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_the_three_http_verbs_call_the_enumerated_routes_and_nothing_else() -> None:
    """**The closed table**, `bin/api.py`'s `OPERATIONS` shape.

    Four verbs over THREE routes, because `dry-run` is `run` with a flag rather
    than a fourth address. A path this table does not name is a path this
    command cannot reach -- asserted by reading every string literal in the
    module and requiring that no other path-shaped one exists.
    """
    module = workflow_module()
    assert module.ROUTES == {
        "run": ("POST", "/workflows/runs"),
        "status": ("GET", "/workflows/runs/{run_id}"),
        "cancel": ("POST", "/workflows/runs/{run_id}/cancel"),
    }

    tree = ast.parse((REPO_ROOT / "bin" / "workflow.py").read_text(encoding="utf-8"))
    declared = {path for _, path in module.ROUTES.values()}
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("/")
        and len(node.value) > 1
        and " " not in node.value
    }
    assert literals <= declared, (
        f"the module names {sorted(literals - declared)}, which `ROUTES` does not"
    )


def test_the_token_comes_from_the_environment_and_never_an_argument(
    outputs: Path, monkeypatch: Any
) -> None:
    """A value in an argument vector is a value `ps` can read (D105, D1160).

    Two halves: the command refuses with exit 3 and a sentence when the
    variable is empty, and the parser has no flag that would accept one.
    """
    module = workflow_module()
    assert module.TOKEN_VARIABLE == "APG_AGENT_TOKEN"  # noqa: S105

    flags = {
        action.option_strings[0]
        for action in module.build_parser()._actions
        if action.option_strings
    }
    assert not {flag for flag in flags if "token" in flag or "secret" in flag}

    monkeypatch.delenv("APG_AGENT_TOKEN", raising=False)
    result = run("run", "--definition", "notes-roundtrip@1", "--project-outputs", str(outputs))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "APG_AGENT_TOKEN is empty" in result.stderr


def test_dry_run_is_run_with_the_flag_set() -> None:
    """One route, one handler, one audit shape.

    Read from the module rather than by dialling: `dry-run` resolves to
    `ROUTES["run"]` and sets `dry_run` from the verb's own name.
    """
    source = (REPO_ROOT / "bin" / "workflow.py").read_text(encoding="utf-8")
    assert '"dry_run": arguments.command == "dry-run"' in source
    assert '_call(\n            base,\n            "run",' in source, (
        "dry-run reaches something other than the `run` route"
    )


def test_a_definition_reference_is_name_at_version(outputs: Path, monkeypatch: Any) -> None:
    """A run names the pair, because no table here holds "the latest"."""
    monkeypatch.setenv("APG_AGENT_TOKEN", "a.token")
    for bad in ("notes-roundtrip", "notes-roundtrip@", "@1", "Notes@1", "notes@1.0.0"):
        result = run("run", "--definition", bad, "--project-outputs", str(outputs))
        assert result.returncode == 2, f"{bad!r} was accepted: {result.stdout}{result.stderr}"
        assert "is not a definition reference" in result.stderr


def test_the_command_holds_no_sql() -> None:
    """A command that could run SQL would be a command a human runs SQL through.

    Asserted over string literals, not over prose: the module's own comments
    name `app_private.workflow_install_definition` to say the deploy calls it.
    """
    tree = ast.parse((REPO_ROOT / "bin" / "workflow.py").read_text(encoding="utf-8"))
    keywords = re.compile(r"\b(select|insert|update|delete|app_private)\b", re.IGNORECASE)
    offenders = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and keywords.search(node.value)
        and not _is_a_docstring(tree, node)
    ]
    assert not offenders, offenders


def _is_a_docstring(tree: ast.Module, node: ast.Constant) -> bool:
    docstrings = set()
    for scope in ast.walk(tree):
        if isinstance(scope, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = scope.body[0] if scope.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return id(node) in docstrings


def test_an_unreachable_service_is_a_prerequisite_and_not_a_refusal(
    outputs: Path, monkeypatch: Any
) -> None:
    """Exit 3, because the deployment could not be asked -- not 5, which would
    say it answered and refused (ADR 0195: a report may not fold an unknown)."""
    monkeypatch.setenv("APG_AGENT_TOKEN", "a.token")
    result = run("status", "--run", "abc", "--project-outputs", str(outputs))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "cannot reach the auth service" in result.stderr


def test_a_document_with_no_app_route_is_reported_rather_than_guessed(tmp_path: Path) -> None:
    """The app route is READ from the document, never rebuilt (ADR 0002)."""
    path = tmp_path / "outputs.json"
    path.write_text(json.dumps({"routes": {}}), encoding="utf-8")
    result = run("status", "--run", "abc", "--project-outputs", str(path))
    assert result.returncode == 5
    assert "publishes no app route" in result.stderr


@pytest.mark.parametrize("verb", ["init", "validate", "run", "dry-run", "status", "cancel"])
def test_every_verbs_help_answers_without_a_project(verb: str) -> None:
    """A verb's help is a READ (D1395, D1402, D1405). It is answered before the
    verb is dispatched, so no parser downstream can refuse it for a missing
    required argument -- including the four whose handler exits 3."""
    result = run(verb, "--help")
    assert result.returncode == 0, result.stderr
    assert len(result.stdout.strip()) > 40
    assert verb.split("-")[0] in result.stdout.lower()


# ---------------------------------------------------------------------------
# The command's own shape
# ---------------------------------------------------------------------------


def test_no_verb_is_an_input_error_and_prints_the_usage() -> None:
    result = run()
    assert result.returncode == 2
    assert "a verb is required" in result.stderr
    assert "Usage:" in result.stderr


def test_the_command_spells_no_address_of_its_own() -> None:
    """The base URL comes from a rendered document; a URL in the command would
    be a second authority for an address `naming` owns (ADR 0002)."""
    source = (REPO_ROOT / "bin" / "workflow.py").read_text(encoding="utf-8")
    assert "https://" not in source
    assert "http://" not in source
