"""The MCP tool catalog, and D274's lesson applied to a document (Session 8, Run 9).

**What D274 actually says is not about HTML.** `/docs/rest` was proved at 401 and
200 for four runs and had never rendered, because every proof asked for the
page's own URL and none had ever asked for **what the page then asks for** -- the
script its own markup names. The generalisation in CLAUDE.md §6 is: *when a page
names an asset, fetch the asset; when a file says a value is derived from
something, grep for the deriver.*

This catalog names no assets. What it names are **tool names, scope names,
ceilings and ADRs**, and the check that corresponds to fetching a page's script
is resolving every one of them against the authority that owns it. A catalog
citing an ADR that does not exist, or naming a scope the vocabulary does not
admit, is the same defect wearing different clothes: a document that reads
correct and is not.

**The generated block is checked in both directions.** A catalog missing a tool
the contract carries misleads a reader about the surface; a catalog carrying a
tool the contract does not is worse, because it describes a capability nobody
approved. `render-mcp-catalog.py --check` is what keeps them equal, and it runs
in the Session 1 gate.

**Every scan here has a control**, because a scan that finds nothing and a scan
that is broken produce the same green.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

CATALOG = REPO_ROOT / "docs" / "mcp-tool-catalog.md"
CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
RENDERER = REPO_ROOT / "bin" / "render-mcp-catalog.py"
DECISIONS = REPO_ROOT / "docs" / "decisions"
CAPABILITY_SCHEMA = REPO_ROOT / "schemas" / "capabilities.schema.json"

BEGIN = "<!-- BEGIN GENERATED: mcp-catalog -->"
END = "<!-- END GENERATED: mcp-catalog -->"


@pytest.fixture(scope="module")
def catalog() -> str:
    return CATALOG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def generated(catalog: str) -> str:
    """Only the generated block. The prose is written and is checked separately."""
    return catalog[catalog.index(BEGIN) + len(BEGIN) : catalog.index(END)]


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# the artifact is derived, and stays derived
# ---------------------------------------------------------------------------


def test_the_catalog_is_current_with_the_contract() -> None:
    """`--check` exits 0, and it is the gate's copy of this assertion.

    Run as a subprocess rather than by importing the renderer: what the gate
    executes is a script with an exit code, and a test that called `render()`
    directly would pass against a script whose `--check` branch was broken.
    """
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"the catalog has drifted from the capability contract:\n{result.stderr}"
    )


def test_the_renderer_check_can_actually_fail(tmp_path) -> None:
    """**Guard the guard.** A `--check` that always exits 0 proves nothing.

    The block is perturbed in a COPY of the repository's catalog path -- via the
    renderer's own module constants -- rather than by editing the tracked file,
    so a failure here cannot leave the working tree dirty.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_render_catalog", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    perturbed = tmp_path / "catalog.md"
    perturbed.write_text(f"{BEGIN}\n\nnot the contract\n\n{END}\n", encoding="utf-8")
    module.CATALOG = perturbed

    assert module.main.__module__  # the attribute exists
    with pytest.raises(SystemExit) as exit_info:
        sys.argv = ["render-mcp-catalog.py", "--check"]
        raise SystemExit(module.main())
    assert exit_info.value.code == 5, "a drifted catalog did not report drift"


def test_the_generated_block_names_exactly_the_contracts_tools(
    generated: str, contract: dict
) -> None:
    """Both directions, and the second is the one that matters.

    A catalog missing a tool misleads a reader about the surface. A catalog
    carrying one the contract does not describes a capability **nobody
    approved**, which is the failure `capabilities.yaml` exists to prevent.
    """
    rows = re.findall(r"^\| `([a-z_]+)` \|", generated, re.MULTILINE)
    named = set(rows)
    in_contract = {tool["name"] for tool in contract["tools"]}

    assert named == in_contract, (
        f"the catalog names {sorted(named)} and the contract carries {sorted(in_contract)}"
    )
    assert len(rows) == len(named) == contract["tool_count"], (
        "a tool is listed twice, or the contract's own tool_count disagrees"
    )


def test_every_resource_ceiling_reaches_the_catalog(generated: str, contract: dict) -> None:
    """The numbers a reader acts on, not merely the names.

    A row ceiling is what a caller plans around and what an operator sizes a
    budget against. A catalog that named the resources and dropped the ceilings
    would read complete.
    """
    for tool in contract["tools"]:
        for resource in tool.get("resources", []):
            assert f"`{resource['name']}`" in generated, resource["name"]
            assert f"**{resource['max_rows']}** rows" in generated, (
                f"{resource['name']}'s ceiling of {resource['max_rows']} is not in the catalog"
            )
            for column in resource["columns"]:
                assert f"`{column}`" in generated, (
                    f"{resource['name']} publishes the column {column!r} and the catalog "
                    "does not name it; a reader would not know it can be projected"
                )


# ---------------------------------------------------------------------------
# D274's shape: everything the document names must resolve
# ---------------------------------------------------------------------------


def test_every_scope_the_catalog_names_is_in_the_closed_vocabulary(catalog: str) -> None:
    """The vocabulary is closed, and the catalog is not allowed to widen it.

    `$defs/agent_scope` in the capability schema is the sole authority (ADR
    0079, ADR 0100). A catalog naming `agent:read` -- which the runbook family
    has proposed more than once -- would document a scope no token can carry.
    """
    schema = json.loads(CAPABILITY_SCHEMA.read_text(encoding="utf-8"))
    permitted = set(schema["$defs"]["agent_scope"]["enum"])
    # `objects:*` is human-only and the catalog names it in order to say so.
    permitted |= {"objects:read", "objects:write"}

    named = set(re.findall(r"`([a-z_]+:[a-z_]+)`", catalog))
    assert named, "no scope was found in the catalog; the scan is broken"

    unknown = sorted(named - permitted)
    assert not unknown, (
        f"the catalog names {unknown}, which the closed vocabulary does not admit. "
        "A scope no token can carry is a capability a reader would try to grant"
    )


def test_every_adr_the_catalog_cites_exists(catalog: str) -> None:
    """**D274, generalised.** When a document names something, resolve it.

    A citation to an ADR that does not exist is not a typo: it is a claim that a
    decision was taken and written down, offered to a reader who has no way to
    check it without this test.
    """
    cited = sorted(set(re.findall(r"ADR (\d{4})", catalog)))
    assert cited, "no ADR citation was found in the catalog; the scan is broken"

    missing = [number for number in cited if not list(DECISIONS.glob(f"{number}-*.md"))]
    assert not missing, f"the catalog cites ADRs that do not exist: {missing}"


def test_that_scan_would_catch_a_fabricated_citation() -> None:
    """**Guard the guard.** The scan above is green when nothing is wrong AND
    when it is looking in the wrong place; only this arm tells them apart."""
    invented = "see ADR 9999 for the reasoning"
    cited = sorted(set(re.findall(r"ADR (\d{4})", invented)))
    assert cited == ["9999"]
    assert not list(DECISIONS.glob("9999-*.md")), "0999 exists; pick another number"


def test_every_divergence_the_catalog_cites_is_recorded(catalog: str) -> None:
    """The other kind of citation, and it resolves against the plans.

    A `D` number is how this repository points at a measurement. One that names
    nothing is a sentence claiming evidence it does not have.
    """
    plans = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((REPO_ROOT / "docs" / "plans").glob("*.md"))
    )
    cited = sorted(set(re.findall(r"\bD(\d{2,3})\b", catalog)))
    assert cited, "no divergence citation was found in the catalog; the scan is broken"

    missing = [number for number in cited if f"**D{number}**" not in plans]
    assert not missing, f"the catalog cites divergences no plan records: {missing}"


# ---------------------------------------------------------------------------
# D421 -- the operator between scopes is the content
# ---------------------------------------------------------------------------


def test_the_scope_expression_tells_any_of_from_all_of(generated: str) -> None:
    """**D421.** A flat list cannot, and a reader deciding a grant has to.

    `query_resource` needs EITHER `notes:read` or `tasks:read`; `run_report`
    needs BOTH. Rendering both as "notes:read, tasks:read" would be true of
    neither, and an operator reading it would over-grant one and under-grant the
    other.
    """
    query = next(line for line in generated.splitlines() if "`query_resource`" in line)
    report = next(line for line in generated.splitlines() if "`run_report`" in line)

    assert " OR " in query and " AND " not in query, f"query_resource renders as: {query}"
    assert " AND " in report and " OR " not in report, f"run_report renders as: {report}"


def test_the_renderer_distinguishes_the_two_shapes_directly() -> None:
    """The same property at the unit level, with both inputs and a control.

    Held here as well as above so that a change to the example contract cannot
    quietly remove the only coverage of the conjunction branch (D332).
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("_render_catalog_unit", RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    any_of = module.scope_expression([["a:read"], ["b:read"]])
    all_of = module.scope_expression([["a:read", "b:read"]])

    assert " OR " in any_of and " AND " not in any_of, any_of
    assert " AND " in all_of and " OR " not in all_of, all_of
    assert any_of != all_of, "the two shapes render identically, which is D421 exactly"


# ---------------------------------------------------------------------------
# the prose, where it states a number
# ---------------------------------------------------------------------------


def test_the_prose_and_the_contract_agree_on_how_many_tools_there_are(
    catalog: str, contract: dict
) -> None:
    """ "Six tools, and there are exactly six" is a claim, so it is checked.

    The generated table is derived and cannot disagree. The sentence above it is
    written by hand, and a seventh tool arriving would leave it saying six while
    the table said seven -- with the contradiction inside one document. This
    tripwire fired exactly as designed when Session 9 Run 3 took the contract
    from four to six, and the prose was rewritten rather than regenerated.
    """
    prose = catalog[: catalog.index(BEGIN)]
    assert contract["tool_count"] == 6, (
        f"the contract now carries {contract['tool_count']} tools; the catalog's prose "
        "says six and has to be rewritten rather than regenerated"
    )
    assert "exactly six" in prose


def test_the_catalog_says_what_the_surface_deliberately_lacks(catalog: str) -> None:
    """A reference that lists only what exists invites the reader to assume the rest.

    Deletes, storage and a runtime-written audit are each absent by decision,
    and each is something a reader would otherwise reasonably expect an agent
    surface with writes to have. Naming them is how the document stops being an
    incomplete list. "No writes" left the list in Session 9 Run 3 -- and must
    STAY gone, because a document claiming no writes above a table listing two
    is the contradiction-in-one-document this file exists to prevent.
    """
    absent = catalog[catalog.index("deliberately absent") :]
    for subject in ("No delete", "No storage", "No durable audit from the runtime"):
        assert subject in absent, f"the catalog does not say {subject.lower()}"
    assert "No writes" not in absent, (
        "the catalog says 'No writes' while the contract carries two; the surface "
        "gained writes in Session 9 Run 3 and the prose has to say what is absent NOW"
    )


def test_the_write_tools_details_reach_the_catalog(generated: str, contract: dict) -> None:
    """The write half of `test_every_resource_ceiling_reaches_the_catalog`.

    The renderer emitted a detail section only for a tool with `resources`, so
    a write tool rendered as a bare table row (Session 9 Run 3) -- and the
    numbers a reader acts on lived only in the contract JSON. The side-effect
    bound, the argument names in order, and what the audit record will not
    carry must all reach the page.
    """
    writes = [tool for tool in contract["tools"] if tool["kind"] == "write"]
    assert writes, "the contract carries no write tool; this test would be vacuous"

    for tool in writes:
        section = generated[generated.index(f"### `{tool['name']}`") :]
        section = section[: section.index("### ", 4)] if "### " in section[4:] else section
        assert f"**{tool['max_affected_rows']}** affected" in section, (
            f"{tool['name']}'s side-effect bound is not in the catalog"
        )
        assert f"`{tool['operation']['operation_id']}`" in section
        rendered_arguments = ", ".join(f"`{argument}`" for argument in tool["arguments"])
        assert rendered_arguments in section, (
            f"{tool['name']}'s arguments are not in the catalog in contract order"
        )
        if tool["audit_redact"]:
            for parameter in tool["audit_redact"]:
                assert f"`{parameter}`" in section, (
                    f"{tool['name']} redacts {parameter!r} and the catalog does not say so"
                )
        else:
            assert "Redacted from the audit record: nothing" in section
    idempotence = {tool["name"]: tool["idempotent"] for tool in writes}
    assert idempotence["create_note"] is False and "not idempotent" in generated
    assert idempotence["update_task_status"] is True
