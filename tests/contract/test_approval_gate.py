"""The approval-gate check: a gated RPC calls `app.require_approval` first (ADR 0242).

`approval_gate.unguarded` joins what nothing else joins -- a compiled capability
contract (which tools are gated, which `/rpc/<name>` each calls) and the body a
project set leaves each `api` function with (`sql_surface.final_function_bodies`).
Its callers answer differently by design (D1868): `bin/mcp-contract.sh check
--project` REFUSES, the render REPORTS and never refuses, and a gated tool
backed by a RELEASE function is reported by both and refused by neither
(D1869).

The proofs over the callers call the product's own command (D1114): the check
through `bin/mcp-contract.py`'s `main`, the render through
`rendering.write_rendered_migrations`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import (
    REPO_ROOT,
    approval_gate,
    capability_manifest,
    config,
    migrations,
    rendering,
    sql_surface,
)

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security]

EXAMPLE_MANIFEST = REPO_ROOT / "project.example.yaml"
SECOND_MANIFEST = REPO_ROOT / "project.second.example.yaml"
FIXTURE = REPO_ROOT / ".generated" / "fixture-alpha-dev"

GUARDED = """
DECLARE
  caller uuid := app.current_user_id();
BEGIN
  PERFORM app.require_approval('gated_tool');
  INSERT INTO app.things (owner_id) VALUES (caller);
END
"""


def _contract(*tools: tuple[str, str, bool]) -> dict[str, Any]:
    """A hand-built contract: `(tool, rpc, requires_approval)` per write tool."""
    return {
        "tools": [
            {
                "name": name,
                "kind": "write",
                "requires_approval": gated,
                "operation": {"method": "post", "path": f"/rpc/{rpc}"},
            }
            for name, rpc, gated in tools
        ]
    }


def _mcp_contract_module():
    name = "_mcp_contract_under_test"
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "bin" / "mcp-contract.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _check(module, manifest: Path) -> int:
    return module.main(["check", "--project", str(manifest)])


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------


def test_a_gated_rpc_that_does_not_call_the_guard_first_is_refused(monkeypatch, capsys) -> None:
    """A gated tool whose function never calls the guard is `absent`, and
    `check --project` exits 5 naming the tool and ADR 0242.

    The command is the product's: the example project's real manifest, with
    the set's final body for `set_note_embedding` replaced by 0003's -- the
    body before the guard existed. The control is the same command over the
    unmodified set, exiting 0, in the same test.
    """
    gated = _contract(("gated_tool", "gated_fn", True), ("open_tool", "open_fn", False))
    bodies = {"gated_fn": GUARDED.replace("PERFORM app.require_approval('gated_tool');", "")}
    bodies["open_fn"] = bodies["gated_fn"]
    findings = approval_gate.unguarded(gated, bodies)
    assert findings == (approval_gate.Finding("gated_tool", "api.gated_fn", "absent"),)
    assert approval_gate.refused(findings) == findings

    module = _mcp_contract_module()
    assert _check(module, EXAMPLE_MANIFEST) == 0, capsys.readouterr().err
    capsys.readouterr()

    third = (
        REPO_ROOT / "projects/example/migrations/templates/0003-note-embedding-events.sql"
    ).read_text(encoding="utf-8")
    before_the_guard = third.split("AS $fn$", 1)[1].split("$fn$", 1)[0]
    real = sql_surface.final_function_bodies

    def without_the_guard(manifest, root):
        bodies = real(manifest, root)
        assert "set_note_embedding" in bodies, sorted(bodies)
        return {**bodies, "set_note_embedding": before_the_guard}

    monkeypatch.setattr(module.sql_surface, "final_function_bodies", without_the_guard)
    assert _check(module, EXAMPLE_MANIFEST) == 5
    printed = capsys.readouterr()
    assert (
        "approval gate: set_note_embedding does not call app.require_approval in "
        "api.set_note_embedding (ADR 0242)" in printed.err
    ), printed.err
    assert printed.err.rstrip().splitlines()[-1].startswith("mcp-contract: the project is refused")
    assert printed.out == "", "a refused check printed its success report"


def test_a_guard_after_another_statement_is_refused() -> None:
    """`not_first`: the guard is there, after something that ran first.

    Comments, whitespace and keyword case do not move the first statement;
    an assignment, a check or another tool's guard before it does. The tool's
    literal is compared exactly, because the guard compares it exactly.
    """
    contract = _contract(("gated_tool", "gated_fn", True))
    accepted = {
        "plain": GUARDED,
        "commented": GUARDED.replace("BEGIN\n", "BEGIN\n  -- the guard first\n  /* always */\n"),
        "lowercase": GUARDED.replace(
            "PERFORM app.require_approval('gated_tool');",
            "perform   app . require_approval ( 'gated_tool' ) ;",
        ),
    }
    for name, body in accepted.items():
        assert approval_gate.unguarded(contract, {"gated_fn": body}) == (), name

    refused = {
        "after_a_check": GUARDED.replace(
            "BEGIN\n",
            "BEGIN\n  IF caller IS NULL THEN RAISE EXCEPTION 'x'; END IF;\n",
        ),
        "after_another_guard": GUARDED.replace(
            "BEGIN\n", "BEGIN\n  PERFORM app.require_approval('other_tool');\n"
        ),
    }
    for name, body in refused.items():
        findings = approval_gate.unguarded(contract, {"gated_fn": body})
        assert findings == (approval_gate.Finding("gated_tool", "api.gated_fn", "not_first"),), name
        assert approval_gate.refused(findings) == findings, name

    wrong_tool = GUARDED.replace("'gated_tool'", "'GATED_TOOL'")
    assert approval_gate.unguarded(contract, {"gated_fn": wrong_tool})[0].reason == "not_first"


def test_a_gated_release_function_is_reported_never_refused(capsys) -> None:
    """D1869: a profile may add an approval to a RELEASE tool, and the database
    cannot read a profile. `project.second.example.yaml` gates
    `update_task_status`; its check exits 0 and prints the line."""
    release = migrations.release_functions(migrations.release_set())
    assert ("api", "update_task_status") in release
    findings = approval_gate.unguarded(
        _contract(("update_task_status", "update_task_status", True)), {}, release
    )
    assert findings == (
        approval_gate.Finding("update_task_status", "api.update_task_status", "release_function"),
    )
    assert approval_gate.refused(findings) == ()

    module = _mcp_contract_module()
    assert _check(module, SECOND_MANIFEST) == 0
    printed = capsys.readouterr()
    assert (
        "mcp-contract: approval gate: update_task_status is gated and backed by the release's "
        "api.update_task_status" in printed.out
    ), printed.out
    assert "ADR 0242, D1869" in printed.out
    assert "refused" not in printed.err


def test_the_render_reports_and_never_refuses(monkeypatch, capsys, tmp_path: Path) -> None:
    """D1868: the render's line is a REPORT. With a finding injected the render
    still writes its migrations and prints one line on stderr; the control is
    the same render with the real (guarded) example set printing none."""
    if not (FIXTURE / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    document = json.loads((FIXTURE / "outputs.json").read_text(encoding="utf-8"))

    control = tmp_path / "control"
    control.mkdir()
    rendering.write_rendered_migrations(control, document)
    assert "approval gate" not in capsys.readouterr().err

    injected = approval_gate.Finding("set_note_embedding", "api.set_note_embedding", "absent")
    monkeypatch.setattr(approval_gate, "unguarded", lambda *_args, **_kwargs: (injected,))
    reported = tmp_path / "reported"
    reported.mkdir()
    written = rendering.write_rendered_migrations(reported, document)
    assert (written / rendering.MIGRATION_MANIFEST_NAME).is_file(), (
        "the render did not finish writing its migrations"
    )
    lines = [line for line in capsys.readouterr().err.splitlines() if "approval gate" in line]
    assert lines == [f"render: {approval_gate.describe(injected)}"], lines


def test_the_example_projects_gated_function_calls_the_guard(capsys) -> None:
    """The example project through its REAL compiled contract and its REAL set:
    one gated tool, its function guarded first, no finding -- and the
    command agrees."""
    manifest = config.load_project_manifest(EXAMPLE_MANIFEST)
    inputs = capability_manifest.project_inputs(manifest)
    assert inputs is not None
    contract = capability_manifest.compile_project_contract(inputs)
    assert approval_gate.gated_functions(contract) == (
        ("set_note_embedding", "set_note_embedding"),
    ), "the example contract gates something else, so this proof proves nothing"

    project_set = migrations.MigrationSet(
        label="project", root=REPO_ROOT / "projects/example/migrations"
    )
    bodies = sql_surface.final_function_bodies(project_set.load_manifest(), project_set.root)
    assert approval_gate.calls_guard_first(bodies["set_note_embedding"], "set_note_embedding")
    release = migrations.release_functions(migrations.release_set())
    assert approval_gate.unguarded(contract, bodies, release) == ()

    module = _mcp_contract_module()
    assert _check(module, EXAMPLE_MANIFEST) == 0
    assert "approval gate" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The body reader
# ---------------------------------------------------------------------------


def _set(tmp_path: Path, *templates: str) -> tuple[dict[str, Any], Path]:
    root = tmp_path / "set"
    (root / "templates").mkdir(parents=True)
    entries = []
    for index, text in enumerate(templates, start=1):
        name = f"{index:04d}-t.sql"
        (root / "templates" / name).write_text(text, encoding="utf-8")
        entries.append({"version": f"2026100112000{index}", "template": f"templates/{name}"})
    return {"migrations": entries}, root


def test_the_body_reader_takes_the_last_definition_in_order(tmp_path: Path) -> None:
    """A replace replaces, a drop removes, a quoted name is read, and a body
    this reader cannot see is recorded EMPTY -- never left out (ADR 0195)."""
    first = (
        "-- migrate:up\nCREATE FUNCTION api.f(p int)\n  RETURNS int LANGUAGE plpgsql AS $fn$\n"
        "BEGIN RETURN 1; END $fn$;\n"
        'CREATE FUNCTION "api" . "g"() RETURNS int LANGUAGE plpgsql AS $body$ BEGIN END $body$;\n'
        "CREATE FUNCTION api.h() RETURNS int LANGUAGE sql AS 'SELECT 1';\n"
        "-- migrate:down\nCREATE FUNCTION api.down_only() RETURNS int AS $x$ $x$;\n"
    )
    second = (
        "-- migrate:up\nCREATE OR REPLACE FUNCTION api.f(p int)\n  RETURNS int LANGUAGE plpgsql "
        "AS $fn$\nBEGIN PERFORM app.require_approval('f'); RETURN 2; END $fn$;\n"
        "DROP FUNCTION IF EXISTS api.g();\n"
    )
    manifest, root = _set(tmp_path, first, second)
    bodies = sql_surface.final_function_bodies(manifest, root)
    assert sorted(bodies) == ["f", "h"], sorted(bodies)
    assert "RETURN 2" in bodies["f"] and "RETURN 1" not in bodies["f"]
    assert bodies["h"] == ""

    contract = _contract(("f", "f", True), ("h", "h", True))
    findings = approval_gate.unguarded(contract, bodies)
    assert findings == (approval_gate.Finding("h", "api.h", "absent"),)
