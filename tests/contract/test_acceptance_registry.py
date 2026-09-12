"""Acceptance registry integrity (runbook §8.4).

This module is the load-bearing consistency check. It runs a real pytest
collection in a subprocess and compares node IDs against the registry, in both
directions. A cheaper implementation — searching each file for the function
name — would pass on a commented-out test, which is exactly the failure this
exists to prevent.

The subprocess is module-scoped and cached, so it runs once. That also means
this module must not be run under xdist, which is consistent with runbook §8.1
leaving parallel execution off by default.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any

import pytest
import yaml

from agentic_postgres import CURRENT_SESSION, REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

REGISTRY = REPO_ROOT / "tests" / "acceptance-registry.yaml"
THREAT_MODEL = REPO_ROOT / "docs" / "threat-model.md"

VALID_PRIORITIES = {"P0", "P1", "P2"}

#: The selector the sweep whose JUnit REPORTS an offline claim runs with --
#: `bin/session-NN-check.sh --mode offline` step 3. It is NOT the Session 1
#: gate's `contract and not future`, and the difference is D1242: this
#: module's first version of the guard below copied the wrong one, so a
#: registered P0 proof sitting in a `p1` module passed every check here and
#: the close's gate still said `not_run`. `test_the_offline_sweep_selector_
#: is_the_newest_gates` keeps this string and that script one fact (D486).
OFFLINE_SWEEP_SELECTOR = "p0 and not future and not live_host and not external"
#: `REL` joined in Session 13 — release identity, the upgrade path, and the
#: operator front door. `IDN` joined in Session 15 — the identity lifecycle:
#: sessions, agent credential expiry, password reset, and the rotation surface.
#: `EVAL` joined in Session 16 — the evaluation harness (ADR 0184).
#: Enumerated rather than patterned, for ADR 0006's reason: a rule that accepted
#: any uppercase word would accept a typo as a new family.
ID_PATTERN = re.compile(
    # `TEN` is Session 20 (ADR 0198): a TENANT extension point -- what an
    # adopter adds, as opposed to what the platform provides. It is its own
    # prefix rather than more `DEP` or `CFG` because the question it answers
    # is whose the thing is, and that is the distinction this session exists
    # to make.
    # `DEV` and `EVD` are Session 22. `DEV` is the developer's own machine --
    # `apg dev`, which is neither a deployment nor anything the fleet knows
    # about, so neither `DEP` nor `OPS` names it. `EVD` is the evidence model
    # itself: ADR 0202's third mode is a property of how a claim is REPORTED
    # rather than of anything the product deploys, and filing it under `OPS`
    # would put a rule about reading evidence in the family that supplies it.
    # `GEN` is Session 23 (ADR 0204): a GENERATED ARTEFACT -- what the product
    # WRITES for a developer to hold, as opposed to what it serves. Neither
    # `DX` nor `DEV` names it: `DX` is the documented path a person walks and
    # `DEV` is the developer's own machine, while this is a file the product
    # emits, carries a digest in, and later refuses at runtime if the surface
    # it was emitted from has moved. A family of its own because the question
    # it answers -- is this artefact still a true claim about that surface --
    # is asked of nothing else here.
    r"^(DEP|CFG|DBX|SEC|API|AGT|STO|REC|OPS|DX|REL|CAP|IDN|EVAL|FLEET|TEN|DEV|EVD|GEN)-[A-Z0-9]+(-\d+)?$"
)


def strip_parameters(node_id: str) -> str:
    """`test_x[case]` and `test_x` name the same test for registry purposes."""
    return re.sub(r"\[.*\]$", "", node_id)


@pytest.fixture(scope="module")
def registry() -> list[dict[str, Any]]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def collected() -> set[str]:
    """Every node ID pytest can actually collect, parameters stripped."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "APG_ACCEPTANCE_SESSION": str(CURRENT_SESSION)},
    )
    assert result.returncode == 0, f"collection failed:\n{result.stdout}\n{result.stderr}"

    return {
        strip_parameters(line.strip())
        for line in result.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    }


@pytest.fixture(scope="module")
def marked_p0() -> set[str]:
    """Node IDs carrying the p0 marker, from a real collection."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header", "-m", "p0"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "APG_ACCEPTANCE_SESSION": str(CURRENT_SESSION)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        strip_parameters(line.strip())
        for line in result.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    }


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_registry_parses_as_a_list(registry: list[dict[str, Any]]) -> None:
    assert isinstance(registry, list)
    assert registry, "the registry is empty"


def test_ids_are_unique(registry: list[dict[str, Any]]) -> None:
    ids = [entry["id"] for entry in registry]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate requirement IDs: {duplicates}"


def test_ids_use_a_registered_prefix(registry: list[dict[str, Any]]) -> None:
    for entry in registry:
        assert ID_PATTERN.match(entry["id"]), f"{entry['id']} is not a valid requirement ID"


def test_every_entry_has_complete_metadata(registry: list[dict[str, Any]]) -> None:
    for entry in registry:
        assert set(entry) == {"id", "priority", "target_session", "test_nodeids", "description"}, (
            f"{entry.get('id')} has unexpected or missing keys: {sorted(entry)}"
        )
        assert entry["priority"] in VALID_PRIORITIES, entry["id"]
        assert isinstance(entry["target_session"], int), entry["id"]
        # **The ceiling is derived, and it was a literal `12` until Session 13.**
        # D719's class, third instance: the evidence writer held the same bound,
        # and Run 2's scan covered `bin/*.py` and not `tests/`. Nothing was wrong
        # while the number it named and the number it meant coincided; the bump
        # is what separated them, and this assertion is what said so.
        assert 1 <= entry["target_session"] <= CURRENT_SESSION, entry["id"]
        assert entry["description"].strip(), f"{entry['id']} has no description"


def test_no_p0_requirement_lacks_a_test(registry: list[dict[str, Any]]) -> None:
    """Runbook §8.4 and §4.6: no P0 guarantee may exist only as prose."""
    for entry in registry:
        if entry["priority"] == "P0":
            assert entry["test_nodeids"], f"{entry['id']} is P0 with no test node ID"


def test_node_ids_are_well_formed(registry: list[dict[str, Any]]) -> None:
    for entry in registry:
        for node_id in entry["test_nodeids"]:
            assert node_id.startswith("tests/"), f"{entry['id']}: {node_id}"
            assert "::" in node_id, f"{entry['id']}: {node_id}"
            assert not node_id.endswith("]"), (
                f"{entry['id']}: {node_id} names one parametrized case; "
                "reference the test without its parameters"
            )


# ---------------------------------------------------------------------------
# Collection — the check that cannot be faked
# ---------------------------------------------------------------------------


def test_every_registered_node_id_is_collectible(
    registry: list[dict[str, Any]], collected: set[str]
) -> None:
    missing = [
        (entry["id"], node_id)
        for entry in registry
        for node_id in entry["test_nodeids"]
        if node_id not in collected
    ]
    assert not missing, f"registry references tests pytest cannot collect: {missing}"


@pytest.fixture(scope="module")
def swept_by_the_gate() -> set[str]:
    """Node IDs the sweep that REPORTS an offline claim actually collects.

    `OFFLINE_SWEEP_SELECTOR`, which is `bin/session-23-check.sh --mode offline`
    step 3 -- the run whose JUnit step 9 computes every offline claim's verdict
    from. **Not** the Session 1 gate's `contract and not future`: that one
    writes Session 1's evidence and nobody else's, and the two selections are
    not the same set (D1242). A second collection costs what one costs and is
    the only way to ask the question this module could not previously ask.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-header",
            "-m",
            OFFLINE_SWEEP_SELECTOR,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "APG_ACCEPTANCE_SESSION": str(CURRENT_SESSION)},
    )
    assert result.returncode == 0, f"collection failed:\n{result.stdout}\n{result.stderr}"
    return {
        strip_parameters(line.strip())
        for line in result.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line
    }


def test_every_offline_claims_proof_is_swept_by_the_gate_that_reports_it(
    registry: list[dict[str, Any]], swept_by_the_gate: set[str]
) -> None:
    """**D1240. Collectible and collected are different questions.**

    Every other test in this module asks whether a registered node id EXISTS --
    `pytest --collect-only` with no selector finds it, so the id is not a typo
    and the test was not renamed out from under the registry. That is worth
    asking and it is not this.

    A claim's verdict is computed from the JUnit of a run that SELECTED BY
    MARKER. `bin/session-01-check.sh` step 4 runs `-m "contract and not
    future"`; CI's Session 2 job runs `-m "p0 and not future and not live_host
    and not external"`. A module carrying no marker at all is collectible by
    name and invisible to both -- so its proofs pass whenever a person names
    the file and are absent from every sweep that reports on them.

    That is what happened. Four modules written in Session 23's Runs 2, 3 and 5
    carried no `pytestmark`, and `write-session-evidence` said so the first time
    their requirements were registered: *"these claims are not proved by this
    run"*, with **no result recorded** for all forty-odd node ids. CI had been
    green on every one of those runs, because nothing selected them.

    Scoped to the claims that are DECLARED OFFLINE, because those are the ones
    an offline gate's JUnit has to carry -- a live claim's proofs are selected
    by their own mode's marker and are checked where that mode runs.

    Goes red if: a module loses its marks, or a new one is written without any;
    or a registered offline proof moves into a module the gate's selector does
    not reach. It cannot be satisfied by renaming a test, which is the failure
    the collectibility tests already cover.
    """
    offline = {
        requirement for claim in claims.OFFLINE_CLAIMS for requirement in claims.CLAIMS[claim]
    }
    entries = [entry for entry in registry if entry["id"] in offline]
    assert entries, "no registered requirement belongs to a declared offline claim"

    unswept: dict[str, list[str]] = {}
    for entry in entries:
        missing = [
            node_id
            for node_id in entry["test_nodeids"]
            # A live half of a requirement that also has an offline half is
            # selected by its own mode's marker, not by this one.
            if node_id.startswith("tests/contract/")
            and strip_parameters(node_id) not in swept_by_the_gate
        ]
        if missing:
            unswept[entry["id"]] = missing

    assert not unswept, (
        "these offline-claim proofs are registered and are NOT collected by "
        f"`-m '{OFFLINE_SWEEP_SELECTOR}'`: {unswept}. They are collectible by "
        "name, which is why the tests above pass; what reports their claim is a "
        "marker-selected sweep, and it does not see them. The usual causes are a "
        "module with no `pytestmark` at all (D1240) and a P0 requirement whose "
        "proof sits in a `p1` module (D1242)"
    )


def test_the_offline_sweep_selector_is_the_newest_gates() -> None:
    """**D1242.** The constant above and the gate are one fact (D486).

    The guard before this one is only as good as the selector it copies, and
    the first version of it copied the Session 1 gate's. Both strings are real
    selectors, both collect thousands of tests, and the wrong one was green --
    so nothing but a comparison with the script can tell them apart.

    Reads the NEWEST `bin/session-NN-check.sh`, because that is the gate a
    session closes on, and asserts the selector appears in it verbatim. A
    session that derives its gate from the last one carries the line across; a
    session that CHANGES the selector gets a red test here and has to move this
    constant deliberately, which is the whole point.
    """
    gates = sorted(
        REPO_ROOT.glob("bin/session-*-check.sh"),
        key=lambda path: int(re.search(r"session-(\d+)-check", path.name).group(1)),
    )
    assert gates, "no session gate found"
    newest = gates[-1]
    text = newest.read_text(encoding="utf-8")
    assert f'run_suite "{OFFLINE_SWEEP_SELECTOR}"' in text, (
        f"{newest.name} does not run its offline sweep with "
        f"`{OFFLINE_SWEEP_SELECTOR}`. Either the gate changed its selector and "
        "OFFLINE_SWEEP_SELECTOR was not moved with it -- in which case the guard "
        "above is asking about a sweep that no longer reports anything -- or the "
        "constant was edited on its own (D1242)"
    )


def test_every_future_placeholder_is_registered(
    registry: list[dict[str, Any]],
    future_markers: dict[str, tuple[int, str]],
    marked_p0: set[str],
) -> None:
    """The reverse direction: a placeholder nobody registered is invisible.

    Membership comes from the ``future`` markers themselves, not from a name
    match. Filtering on ``"test_future" in node_id`` would sweep in active
    Session 1 tests such as ``test_future_stub_exits_ten``, which assert that
    the *stubs* behave and are real work.
    """
    registered = {node_id for entry in registry for node_id in entry["test_nodeids"]}
    unregistered = sorted(node_id for node_id in future_markers if node_id not in registered)
    assert not unregistered, f"future placeholders missing from the registry: {unregistered}"

    uncollected = sorted(node_id for node_id in future_markers if node_id not in marked_p0)
    assert not uncollected, f"placeholders not collected under the p0 marker: {uncollected}"


def test_collection_succeeds_for_the_whole_suite(collected: set[str]) -> None:
    assert len(collected) > 100, f"only {len(collected)} tests collected; expected the full suite"


# ---------------------------------------------------------------------------
# Session gate policy (runbook §8.4, §4.6)
# ---------------------------------------------------------------------------


def test_no_requirement_at_or_before_the_gate_session_remains_future(
    registry: list[dict[str, Any]],
    future_markers: dict[str, tuple[int, str]],
    gate_session: int,
) -> None:
    """Runbook §8.4: a requirement due by now may not still be a placeholder."""
    still_future = {requirement for _, requirement in future_markers.values()}
    overdue = sorted(
        entry["id"]
        for entry in registry
        if entry["target_session"] <= gate_session and entry["id"] in still_future
    )
    assert not overdue, (
        f"requirements targeted at session {gate_session} or earlier still marked future: {overdue}"
    )


def test_session_one_requirements_are_active(
    registry: list[dict[str, Any]], future_markers: dict[str, tuple[int, str]]
) -> None:
    """A Session 1 requirement may not be satisfied by a placeholder.

    Checked against the actual marker set rather than by name: several active
    Session 1 tests are named ``test_future_stub_*`` because they assert that
    the *stubs* behave, and those are real work.
    """
    session_one = [entry for entry in registry if entry["target_session"] == 1]
    assert session_one, "no Session 1 requirements are registered"
    for entry in session_one:
        for node_id in entry["test_nodeids"]:
            assert node_id not in future_markers, f"{entry['id']} points at a placeholder"


# ---------------------------------------------------------------------------
# Threat model referential integrity (implementation plan §3)
# ---------------------------------------------------------------------------


def parse_threat_table() -> list[dict[str, str]]:
    """Parse only the ID columns. The analysis itself is not machine-checked."""
    rows: list[dict[str, str]] = []
    headers: list[str] = []

    for line in THREAT_MODEL.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not headers:
            headers = cells
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def test_threat_model_table_has_the_required_columns() -> None:
    rows = parse_threat_table()
    assert rows, "no threat rows found; the table format may have changed"
    for column in (
        "Threat ID",
        "Attacker capability",
        "Protected asset",
        "Prevention",
        "Detection",
        "Residual risk",
        "Acceptance requirement IDs",
        "Acceptance test node IDs",
        "Target session",
    ):
        assert column in rows[0], f"threat model is missing the {column!r} column"


def test_threat_model_node_ids_are_collectible(collected: set[str]) -> None:
    unknown: list[str] = []
    for row in parse_threat_table():
        for node_id in row["Acceptance test node IDs"].replace("`", "").split(","):
            node_id = node_id.strip()
            if node_id and strip_parameters(node_id) not in collected:
                unknown.append(f"{row['Threat ID']}: {node_id}")
    assert not unknown, f"threat model references uncollectible tests: {unknown}"


def test_threat_model_requirement_ids_exist_in_the_registry(
    registry: list[dict[str, Any]],
) -> None:
    known = {entry["id"] for entry in registry}
    unknown: list[str] = []
    for row in parse_threat_table():
        for identifier in row["Acceptance requirement IDs"].replace("`", "").split(","):
            identifier = identifier.strip()
            if identifier and identifier not in known:
                unknown.append(f"{row['Threat ID']}: {identifier}")
    assert not unknown, f"threat model references unregistered requirements: {unknown}"


def test_every_threat_row_names_at_least_one_requirement() -> None:
    for row in parse_threat_table():
        assert row["Acceptance requirement IDs"].strip(), (
            f"{row['Threat ID']} claims a control with no acceptance requirement"
        )


# ---------------------------------------------------------------------------
# Generated documentation is derived from this file
# ---------------------------------------------------------------------------


def test_acceptance_matrix_is_generated_from_the_registry() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "bin" / "render-acceptance-matrix.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_product_contract_requirement_table_is_generated() -> None:
    text = (REPO_ROOT / "docs" / "product-contract.md").read_text(encoding="utf-8")
    assert "<!-- BEGIN GENERATED: requirements -->" in text
    for entry in yaml.safe_load(REGISTRY.read_text(encoding="utf-8")):
        if entry["priority"] == "P0":
            assert entry["id"] in text, f"{entry['id']} is absent from the generated table"


def test_every_adr_is_indexed() -> None:
    """An unlisted ADR is one nobody reads, and 0004 went unlisted for a session.

    Checked against the filesystem rather than against a hard-coded count, so
    the next ADR is covered the moment it is written.
    """
    decisions = REPO_ROOT / "docs" / "decisions"
    index = (decisions / "README.md").read_text(encoding="utf-8")
    missing = [
        path.name
        for path in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if f"({path.name})" not in index
    ]
    assert not missing, f"ADRs absent from docs/decisions/README.md: {missing}"


#: Both spellings the ADRs use for their status line. 0001-0036 write
#: ``- **Status:** Accepted``; 0037 onward write ``Status: accepted``. Two
#: formats is a wart, and normalising the files would be a large diff over
#: settled decisions for no gain — so the reader handles both and the check
#: below is what actually matters.
_STATUS_LINE = re.compile(r"^(?:-\s*\*\*Status:\*\*|Status:)\s*(.+)$", re.MULTILINE)


def _declared_status(text: str) -> str:
    """The first word of an ADR's own status line, lowercased.

    The first word only: an ADR records its qualifications in the rest of the
    line — ``accepted; the publication clause superseded by 0044`` — and the
    index has room for a short form. Comparing whole strings would force the two
    to be transcriptions of each other, which is how a table stops being updated.
    """
    match = _STATUS_LINE.search(text)
    assert match, "no status line"
    return match.group(1).strip().strip(".").split()[0].rstrip(";,").lower()


def test_the_index_status_agrees_with_each_adr() -> None:
    """An index that says ``Proposed`` about a decision the host is running.

    ``test_every_adr_is_indexed`` checks that a row exists. Nothing checked what
    the row said, and by the end of Session 4 three of them said ``Proposed``
    about ADRs that had been built, deployed and measured for nine runs — 0041
    still said so in its own header too. The index is the document the project
    contract points a reader at, so a stale status there is a wrong answer given
    confidently.

    Compared on the first word, so ``accepted; superseded in part`` in the file
    and ``Accepted, superseded in part`` in the row agree.
    """
    decisions = REPO_ROOT / "docs" / "decisions"
    index = (decisions / "README.md").read_text(encoding="utf-8")
    rows = {}
    for line in index.splitlines():
        if not line.startswith("| ["):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 4 and (name := re.search(r"\((\d{4}-[a-z0-9-]+\.md)\)", cells[0])):
            rows[name.group(1)] = cells[3]

    disagreements = []
    for path in sorted(decisions.glob("[0-9][0-9][0-9][0-9]-*.md")):
        declared = _declared_status(path.read_text(encoding="utf-8"))
        listed = rows.get(path.name, "").split(",")[0].strip().lower()
        if declared != listed:
            disagreements.append(f"{path.name}: file says {declared!r}, index says {listed!r}")
    assert not disagreements, disagreements


def test_no_source_file_cites_a_missing_adr() -> None:
    """The reverse direction: a citation of an ADR that does not exist.

    Session 1 shipped four such citations -- decisions B, C, E and F each named
    an ADR file that was never written -- and nothing detected it for a session.
    """
    existing = {
        path.name for path in (REPO_ROOT / "docs" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")
    }
    cited: set[str] = set()
    for root in ("src", "bin", "schemas", "tests"):
        for path in (REPO_ROOT / root).rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sh", ".json", ".yaml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            cited.update(re.findall(r"\b(\d{4}-[a-z0-9-]+\.md)\b", text))

    dangling = sorted(cited - existing)
    assert not dangling, f"source cites ADRs that do not exist: {dangling}"


def test_registry_file_is_the_only_place_ids_are_created() -> None:
    """Guard against a second catalog appearing somewhere else."""
    others = [
        path
        for path in (REPO_ROOT / "src").rglob("*.py")
        if "CFG-001" in path.read_text(encoding="utf-8")
    ]
    assert not others, f"requirement IDs are hard-coded in source: {others}"
