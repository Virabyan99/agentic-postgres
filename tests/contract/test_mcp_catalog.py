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
    module = _renderer_module("_render_catalog_perturbed")

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
    in_contract = {tool["name"] for tool in contract["tools"]}

    # **Two tables now, with different row semantics** (ADR 0177). The summary
    # names each tool once; the capability table names it once per backing
    # authorization, so `query_resource` appears twice there and must. Counting
    # both together made "a tool is listed twice" fire on a catalog that was
    # right, so the count is asserted per table rather than dropped.
    summary = re.findall(r"^\| `([a-z_]+)` \| (?:read|write|metadata) \|", generated, re.MULTILINE)
    detail = re.findall(r"^\| `([a-z_]+)` \| `([a-z_]+)` \|", generated, re.MULTILINE)

    assert set(summary) == in_contract, (
        f"the summary names {sorted(set(summary))} and the contract carries {sorted(in_contract)}"
    )
    assert len(summary) == len(set(summary)) == contract["tool_count"], (
        "a tool is listed twice in the summary, or the contract's own tool_count disagrees"
    )

    if contract["schema_version"] >= 2:
        assert {tool for tool, _ in detail} == in_contract, (
            f"the capability table names {sorted({tool for tool, _ in detail})}"
        )
        assert len(detail) == contract["capability_count"], (
            f"the capability table carries {len(detail)} rows and the contract declares "
            f"{contract['capability_count']} capabilities"
        )
        # The grouped tool is the whole reason the two tables differ (ADR 0120).
        assert sum(1 for tool, _ in detail if tool == "query_resource") == 2, (
            "the grouped tool no longer shows both of its authorizations, which is "
            "the case that makes a per-capability table necessary at all"
        )
    else:
        assert not detail, "a v1 contract rendered a capability table it cannot fill"


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
    module = _renderer_module("_render_catalog_unit")

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
    """The prose states no count, and the rendered line states the contract's.

    **Replaced under ADR 0200.** This asserted *"exactly six"* in the
    hand-written prose, and that tripwire fired exactly as designed when
    Session 9 Run 3 took the contract from four to six. Since ADR 0200 a
    project's lock may carry more tools than the release's (ADR 0201), so a
    number written by hand would be right for exactly one deployment: the
    rendered line carries the count, and the prose is checked NOT to.
    """
    prose = catalog[: catalog.index(BEGIN)]
    generated = catalog[catalog.index(BEGIN) :]
    assert f"**{contract['tool_count']} tools**" in generated
    assert contract["tool_count"] == len(contract["tools"])
    for claim in ("exactly six", "Six tools", "six tools"):
        assert claim not in prose, f"the prose states a count by hand: {claim!r}"


def test_the_catalog_says_what_the_surface_deliberately_lacks(catalog: str) -> None:
    """A reference that lists only what exists invites the reader to assume the rest.

    Deletes and storage are each absent by decision, and each is something a
    reader would otherwise reasonably expect an agent surface with writes to
    have. Naming them is how the document stops being an incomplete list.

    **Two sentences have left this list, each in the run that built the thing,
    and this test is how both were noticed.** "No writes" went in Session 9
    Run 3; "No durable audit from the runtime" went in Run 6, which built it
    (ADR 0141) -- and this assertion is what fired to say so. Both must STAY
    gone: a document claiming no writes above a table listing two, or no audit
    above a surface that records every call, is the contradiction-in-one-document
    this file exists to prevent.

    **What replaced the audit sentence is asserted too**, because a section that
    only ever shrinks stops being a list of absences. The record's own limits --
    the span it does not reach, and the retention nobody has decided -- are now
    the honest remainder.
    """
    absent = catalog[catalog.index("deliberately absent") :]
    for subject in ("No delete", "No storage"):
        assert subject in absent, f"the catalog does not say {subject.lower()}"

    for gone, why in (
        ("No writes", "the contract has carried two since Run 3"),
        ("No durable audit from the runtime", "Run 6 built it (ADR 0141)"),
        (
            "does **not** span ingress",
            "Session 11 Run 5 closed that leg (ADR 0160)",
        ),
    ):
        assert gone not in absent, f"the catalog still says {gone!r}, and {why}"

    assert "prunes" in absent, "retention is still undecided and the catalog must say so"


def test_the_catalog_describes_the_request_id_span_it_now_has(catalog: str) -> None:
    """**The third sentence to leave the absence list, and its replacement.**

    Until Session 11 the catalog said the request id *"does not span ingress —
    that is `OPS-LOG-001`, Session 11's — and the database-written row carries
    none (D500)"*, and a test asserted that boundary was stated. Both halves are
    now closed: Run 5 stamps the id on the response, where Traefik's access log
    keeps it as `downstream_X-Request-Id` (ADR 0160), and Run 6's migration 0022
    puts it on the `database` row (ADR 0161).

    This is the stricter replacement §6 requires. The old assertion could fail
    one way — the boundary going unmentioned. This fails three: a catalog that
    does not describe the span, one that does not say inbound headers are
    ignored, or one that omits the correlation caveat an operator needs.
    """
    assert "ingress" in catalog, "the catalog does not describe the span the id now has"

    assert "inbound" in catalog.lower() and "ignores" in catalog.lower(), (
        "the catalog does not say an inbound X-Request-Id is ignored. A reader who "
        "assumed their own header was adopted would correlate against a value this "
        "deployment never used (ADR 0160)"
    )

    # D649's obligation, and the reason it is asserted rather than trusted: a
    # caller reaching PostgREST directly chooses the id on its own `database`
    # row, so correlating by request id alone can gather one agent's rows under
    # another agent's request. The row still names its author.
    assert "agent_id" in catalog, (
        "the catalog does not tell an operator to read agent_id beside request_id. "
        "A direct caller supplies the header that becomes its own database row's "
        "id, and that is only harmless because the mismatch is visible (ADR 0161)"
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


def test_the_renderers_reserved_parameters_match_the_runtimes(generated: str) -> None:
    """Two lists that must agree, and a test between them (D486, ADR 0181).

    A write tool requires one parameter the CONTRACT does not carry, because it
    is not a database function argument -- `idempotency_key` travels as a header
    and never enters the request body. The catalog publishes what an agent can do
    against this deployment, so a required parameter it does not mention makes
    the document wrong in the direction a reader cannot detect (D274's family).

    `bin/render-mcp-catalog.py` keeps its own copy rather than importing the
    service package from the repository root, so this compares the two. Aliasing
    one to the other would make this test compare a value with itself, which is
    the shape §6 names -- and the renderer is the half a reader of the catalog
    actually depends on.
    """
    import sys as _sys

    service = REPO_ROOT / "services" / "auth-api"
    _sys.path.insert(0, str(service))
    try:
        from app import mcp_tools
    finally:
        _sys.path.remove(str(service))

    module = _renderer_module("_render_catalog_reserved")

    assert module.RESERVED_WRITE_PARAMETERS == mcp_tools.RESERVED_WRITE_PARAMETERS, (
        "the catalog renderer and the runtime disagree about which parameters a write "
        "tool requires beyond the contract's arguments"
    )
    assert mcp_tools.RESERVED_WRITE_PARAMETERS, (
        "the reserved list is empty, so the comparison above holds vacuously"
    )
    for parameter in module.RESERVED_WRITE_PARAMETERS:
        assert f"`{parameter}`" in generated, (
            f"{parameter!r} is required of every write and the catalog does not name it"
        )


# ---------------------------------------------------------------------------
# A project's own catalog (Session 25, ADR 0201, D1309)
# ---------------------------------------------------------------------------


PROJECT_MANIFEST = REPO_ROOT / "project.example.yaml"
PROJECT_CONTRACT = (
    REPO_ROOT / "projects" / "example" / "contracts" / "mcp-capabilities.canonical.json"
)
PROJECT_CATALOG = REPO_ROOT / "projects" / "example" / "docs" / "mcp-tool-catalog.md"


def _renderer_module(name: str = "_render_catalog"):
    """The renderer, imported by path, so a test can reach its constants.

    A fresh instance per call, under a caller-chosen name: three proofs here
    rebind one of the module's constants, and a shared instance would make each
    depend on what the last one left behind.

    **It is REGISTERED in `sys.modules`, and that is not a formality.**
    `@dataclass` resolves its own class's module through
    `sys.modules[cls.__module__]` while the class is being created, so a module
    loaded by path and never registered there makes `dataclasses` read
    `None.__dict__`. Three proofs in this file used the unregistered idiom and
    were green for seventeen sessions; the first dataclass the renderer gained
    (Session 25's `Target`) turned all three red at import, before any
    assertion. importlib's own documentation prescribes the registration, and
    the name is the caller's so nothing collides.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def project_contract() -> dict:
    return json.loads(PROJECT_CONTRACT.read_text(encoding="utf-8"))


def test_a_project_catalog_is_rendered_from_the_projects_contract(
    project_contract: dict, contract: dict
) -> None:
    """**D1309.** A tenant's tools appeared in no rendered document.

    `render-mcp-catalog.py` read one contract and wrote one file, so an adopter
    who followed README's *Giving an agent your tables* ended with two tools
    nothing described. The release's catalog does not describe them and cannot:
    it is rendered from the release's contract, which does not carry them.

    What is asserted here is that the project's catalog is **derived from the
    project's contract** -- every tool, and no other -- and that its opening
    lines say what it is not. A catalog of a project's two tools under the same
    heading the release's six use would tell a reader their deployment serves
    two, which is the failure mode this whole module exists to prevent, one
    level down.

    The tool names are read out of the contract rather than typed. The **count**
    is asserted against 2 as well, because a contract that had quietly emptied
    would satisfy "every tool it carries is in the table" with nothing on either
    side (D374, and D1324: the plan said seven, which is the release's
    capability count read off the wrong document).
    """
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check", "--project", str(PROJECT_MANIFEST)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"the example project's catalog has drifted from its contract:\n{result.stderr}"
    )

    text = PROJECT_CATALOG.read_text(encoding="utf-8")
    block = text[text.index(BEGIN) + len(BEGIN) : text.index(END)]

    names = sorted(tool["name"] for tool in project_contract["tools"])
    assert len(names) == 2, (
        f"the example project's contract carries {len(names)} tools ({names}); this proof was "
        "written against the two it has, and a contract that emptied would pass every "
        "assertion below about nothing"
    )
    for name in names:
        assert f"`{name}`" in block, f"the project catalog does not name its own tool {name}"

    # What it is NOT. Each of these is a sentence the header derives.
    assert "Project `example`" in block, "the project catalog does not name the project"
    assert "not the whole of what its deployment serves" in block, (
        "the project catalog does not say the release's tools are served beside these, so a "
        "reader would take two tools for the whole agent surface"
    )
    link = "../../../docs/mcp-tool-catalog.md"
    assert link in block, "the project catalog does not point at the release's"
    assert (PROJECT_CATALOG.parent / link).resolve() == CATALOG, (
        f"the project catalog's link to the release's does not resolve: {link}"
    )

    # The shared name, marked. `query_resource` is one name over two contracts
    # and two authorizations, and a reader granting a scope has to know.
    shared = sorted({tool["name"] for tool in contract["tools"]} & set(names))
    assert shared == ["query_resource"], (
        f"the two contracts share {shared}; this assertion is written against the one name "
        "they shared when it was written, and a change to that set changes what the header "
        "must say"
    )
    assert "different authorizations under one name" in block, (
        "the project catalog does not mark the tool name the release also serves"
    )

    # And the release's catalog is still the release's: it names none of the
    # project's own tools, which is the half D1309 measured.
    release_catalog = CATALOG.read_text(encoding="utf-8")
    assert "set_note_embedding" not in release_catalog, (
        "the release's catalog names a project's tool; the two documents have merged"
    )


def test_check_project_refuses_a_stale_catalog(tmp_path, monkeypatch) -> None:
    """**Guard the guard, for the project path, and D1325's arm with it.**

    Three answers are checked, because the renderer has three and the middle one
    did not exist until this run: a catalog that is **absent** is reported with
    the command that writes it, a catalog that has **drifted** exits 5, and a
    catalog that is current exits 0. Before ADR 0195 was applied here the absent
    case raised `FileNotFoundError` -- `main` read its output before writing it,
    and a project's first catalog is exactly the absent case, so the first thing
    an adopter would have seen was a traceback.

    The output path is redirected through the renderer's own `PROJECT_CATALOG`
    constant, which `project_target` joins onto `projects/<slug>`; an absolute
    value replaces the join, so the project's real contract is resolved and read
    for real while nothing is written inside the checkout. The tracked catalog
    is asserted untouched at the end rather than assumed.
    """
    before = PROJECT_CATALOG.read_bytes()
    module = _renderer_module("_render_catalog_project")
    redirected = tmp_path / "catalog.md"
    module.PROJECT_CATALOG = redirected

    def run(*arguments: str) -> tuple[int, str]:
        monkeypatch.setattr(
            sys, "argv", ["render-mcp-catalog.py", *arguments, "--project", str(PROJECT_MANIFEST)]
        )
        import contextlib
        import io

        err = io.StringIO()
        out = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = module.main()
        return code, err.getvalue() + out.getvalue()

    code, message = run("--check")
    assert code == 5, "a catalog that does not exist was not reported"
    assert "does not exist" in message and "--write" in message, (
        f"the absent catalog was reported without the command that writes it: {message!r}"
    )

    code, _ = run("--write")
    assert code == 0 and redirected.is_file(), "--write --project did not create the catalog"
    code, _ = run("--check")
    assert code == 0, "the catalog it just wrote is not current"

    # One byte, in the generated block.
    stale = redirected.read_text(encoding="utf-8").replace("**2 tools**", "**3 tools**", 1)
    assert stale != redirected.read_text(encoding="utf-8"), (
        "the perturbation matched nothing, so the drift below is not being tested"
    )
    redirected.write_text(stale, encoding="utf-8")
    code, message = run("--check")
    assert code == 5, "a drifted project catalog did not report drift"
    assert "has drifted" in message and "mcp-capabilities.canonical.json" in message, (
        f"the drift was reported without naming the contract it drifted from: {message!r}"
    )

    assert PROJECT_CATALOG.read_bytes() == before, (
        "this proof wrote inside the checkout; the redirection did not hold"
    )
