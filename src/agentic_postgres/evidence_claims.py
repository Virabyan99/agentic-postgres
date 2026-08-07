"""Named claims, and the acceptance requirements that prove them.

Session 2's evidence recorded ``{"tests": {"host_suite": "passed"}}`` — the name
of the suite that ran, not the name of anything it proved. A reader learning
that "the host suite passed" learns which command exited zero and nothing about
whether secrets stayed in, or whether two projects stayed apart. The plan's own
Run 8 check asks for ``.tests.isolation`` and ``.tests.secret_leakage``, keys no
version of the writer could produce.

A **claim** is a guarantee stated in the words the session is about. It is not a
new authority: it names acceptance-registry requirement IDs, and its verdict is
computed from the JUnit results of exactly the node IDs that registry lists. So
a requirement that gains a test gains it here too, and a claim cannot quietly
come to mean less than it did.

Three rules keep a claim from being weaker than it looks.

**Absence is not success.** A node ID the registry lists and the JUnit file does
not contain makes the claim ``not_run``, never ``passed``. A suite that stopped
collecting a test would otherwise report the claim green on what remained.

**A skip is not a pass.** ``requires_environment`` skips are how the deployment
tests behave in a checkout, which is correct there and worthless as evidence.

**Each claim is measured in one environment.** Its live proofs carry exactly one
of ``live_host`` or ``external``, so the mode that can prove it is derived
rather than declared, and a claim whose proofs straddle both environments is an
error rather than a half-measured verdict.
"""

from __future__ import annotations

import ast
import xml.etree.ElementTree as ElementTree
from functools import cache
from pathlib import Path

import yaml

from agentic_postgres import REPO_ROOT

TESTS_ROOT = REPO_ROOT / "tests"
REGISTRY_PATH = TESTS_ROOT / "acceptance-registry.yaml"

#: Gate mode -> the pytest marker its suite selects. ``offline`` is absent on
#: purpose: a claim proved only by tests that need no environment is a claim
#: about a checkout, and Session 2's are about a running deployment.
MODE_MARKERS = {"host": "live_host", "external": "external"}

#: Claim name -> the acceptance requirements whose tests prove it.
#:
#: The two the Session 2 plan's Run 8 checks by name, and no more. A
#: ``public_boundary`` claim over ``SEC-NET-001`` was written and removed: that
#: requirement's proofs include an IPv6 scan, the deployment host holds a global
#: IPv6 address, and no network available to run the external gate from has IPv6
#: transit. The claim could only ever come out ``failed`` — not because the
#: boundary is open but because nobody can look at it from here — and a claim
#: that cannot pass is a blocker invented by the evidence writer. The gap is
#: recorded as a divergence and in ``docs/host-baseline.md`` instead, which is
#: what an unmeasured surface deserves. Both modes stay implemented, so the day
#: a scan can be run from an IPv6 network the claim is three lines.
CLAIMS: dict[str, tuple[str, ...]] = {
    "isolation": ("DEP-ISO-002",),
    "secret_leakage": ("SEC-SECRET-001", "SEC-SECRET-002"),
}

#: Worst-first, so combining two observations of one test is a max().
_SEVERITY = ("failed", "skipped", "passed")


class ClaimError(RuntimeError):
    """A claim cannot be resolved. No verdict is produced for it."""


# ---------------------------------------------------------------------------
# The registry side
# ---------------------------------------------------------------------------


@cache
def _registry() -> dict[str, tuple[str, ...]]:
    entries = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not entries:
        raise ClaimError(f"{REGISTRY_PATH} is empty")
    return {entry["id"]: tuple(entry.get("test_nodeids") or ()) for entry in entries}


def requirement_nodeids(requirement: str) -> tuple[str, ...]:
    try:
        nodeids = _registry()[requirement]
    except KeyError:
        raise ClaimError(f"{requirement} is not in the acceptance registry") from None
    if not nodeids:
        raise ClaimError(f"{requirement} lists no test node IDs")
    return nodeids


def claim_nodeids(claim: str) -> tuple[str, ...]:
    """Every node ID that proves a claim, in registry order, without duplicates."""
    if claim not in CLAIMS:
        raise ClaimError(f"unknown claim: {claim}")
    seen: dict[str, None] = {}
    for requirement in CLAIMS[claim]:
        for nodeid in requirement_nodeids(requirement):
            seen[nodeid] = None
    return tuple(seen)


# ---------------------------------------------------------------------------
# Which environment a test needs
# ---------------------------------------------------------------------------


def _decorator_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return target.attr if isinstance(target, ast.Attribute) else None


@cache
def _environment_markers() -> dict[str, frozenset[str]]:
    """``path::test_name`` -> the environment markers it carries.

    Parsed with ``ast`` rather than by collecting with pytest, for the reason
    ``tests/conftest.py`` parses its ``future`` markers the same way: importing
    a test module executes it, and this runs inside the evidence writer, which
    must not be able to start a socket by reading a file.

    ``tests/contract/test_environment_gates.py`` performs a similar scan for a
    different question — whether every live test declares the variable it needs.
    That one polices the tests; this one reports where a claim can be measured.
    Merging them would put a test-suite policy check inside the library the
    writer imports.
    """
    wanted = set(MODE_MARKERS.values())
    found: dict[str, frozenset[str]] = {}

    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        module_level: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets
            ):
                if isinstance(node.value, ast.List):
                    module_level |= {
                        name
                        for entry in node.value.elts
                        if (name := _decorator_name(entry)) in wanted
                    }

        relative = path.relative_to(REPO_ROOT).as_posix()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            markers = set(module_level)
            markers |= {
                name
                for decorator in node.decorator_list
                if (name := _decorator_name(decorator)) in wanted
            }
            found[f"{relative}::{node.name}"] = frozenset(markers)

    return found


def environment_markers(nodeid: str) -> frozenset[str]:
    markers = _environment_markers().get(nodeid)
    if markers is None:
        raise ClaimError(
            f"{nodeid} names no test function in {TESTS_ROOT.name}/. "
            "The acceptance registry and the suite have drifted apart."
        )
    return markers


def claim_mode(claim: str) -> str:
    """The one gate mode that can run a claim's live proofs.

    Derived from the markers rather than declared beside the claim, so a test
    that moves between environments moves its claim with it.
    """
    markers = {marker for nodeid in claim_nodeids(claim) for marker in environment_markers(nodeid)}
    modes = sorted(mode for mode, marker in MODE_MARKERS.items() if marker in markers)
    if not modes:
        raise ClaimError(
            f"claim {claim!r} has no live proof: every test it names runs in a checkout, "
            "so no deployment is being measured."
        )
    if len(modes) > 1:
        raise ClaimError(
            f"claim {claim!r} spans {modes}. One evidence half would have to report a "
            "verdict on tests it could not run."
        )
    return modes[0]


def claims_for_mode(mode: str) -> tuple[str, ...]:
    if mode not in MODE_MARKERS:
        raise ClaimError(f"unknown mode: {mode}. Expected one of {sorted(MODE_MARKERS)}.")
    return tuple(claim for claim in sorted(CLAIMS) if claim_mode(claim) == mode)


def static_nodeids_for_mode(mode: str) -> tuple[str, ...]:
    """The claim proofs of ``mode`` that carry no environment marker.

    They run anywhere, so the mode's own ``-m live_host`` (or ``-m external``)
    selector does not collect them, and a claim that needed them would come out
    ``not_run`` forever. The gate runs these explicitly rather than widening the
    selector, which would drag the whole contract suite into a deployment run.

    Empty is a legitimate answer, and means this mode carries no claim. The
    caller must not read it as "run everything": ``pytest`` with no node IDs
    collects the entire suite.
    """
    nodeids: dict[str, None] = {}
    for claim in claims_for_mode(mode):
        for nodeid in claim_nodeids(claim):
            if not environment_markers(nodeid):
                nodeids[nodeid] = None
    return tuple(sorted(nodeids))


# ---------------------------------------------------------------------------
# The JUnit side
# ---------------------------------------------------------------------------


def junit_key(nodeid: str) -> tuple[str, str]:
    """``path::Class::test`` -> the ``(classname, name)`` pytest writes for it.

    Looking a known node ID up in the XML, rather than reconstructing node IDs
    out of it: ``xunit2`` — pytest's default family since 6.0 — writes no
    ``file`` attribute, so the reverse direction cannot tell a package component
    from a class one.
    """
    path, *rest = nodeid.split("::")
    if not rest:
        raise ClaimError(f"{nodeid} names a file, not a test")
    module = path.removesuffix(".py").replace("/", ".")
    return ".".join([module, *rest[:-1]]), rest[-1]


def _worst(left: str, right: str) -> str:
    return min(left, right, key=_SEVERITY.index)


def junit_outcomes(paths: list[Path]) -> dict[tuple[str, str], str]:
    """``(classname, name)`` -> the worst outcome recorded for it.

    Parameter cases collapse onto their base name, because the registry says a
    node ID naming a parametrized test refers to all of its cases. Worst wins:
    one failing case is a failing test.
    """
    outcomes: dict[tuple[str, str], str] = {}
    for path in paths:
        if not path.is_file():
            raise ClaimError(f"required test artifact is missing: {path}")
        try:
            # S314: JUnit XML this repository's own pytest run produced moments
            # earlier, under a path the gate controls -- the same judgement
            # evidence.parse_junit records.
            root = ElementTree.fromstring(path.read_text(encoding="utf-8"))  # noqa: S314
        except ElementTree.ParseError as exc:
            raise ClaimError(f"{path} is not parseable JUnit XML: {exc}") from exc

        for case in root.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            key = (case.get("classname", ""), case.get("name", "").split("[", 1)[0])
            outcomes[key] = _worst(outcomes.get(key, "passed"), outcome)

    if not outcomes:
        raise ClaimError(f"no test case was recorded in {[str(path) for path in paths]}")
    return outcomes


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def claim_result(claim: str, outcomes: dict[tuple[str, str], str]) -> dict[str, object]:
    """One claim's verdict, with the node IDs behind it.

    ``not_run`` is a distinct status from ``failed`` and is reported whenever a
    proof is absent, even if every proof that did run passed. The difference
    matters to whoever reads the evidence: ``failed`` means the system is wrong,
    ``not_run`` means the evidence is.
    """
    nodeids = claim_nodeids(claim)
    missing = [nodeid for nodeid in nodeids if junit_key(nodeid) not in outcomes]
    worst = "passed"
    for nodeid in nodeids:
        outcome = outcomes.get(junit_key(nodeid))
        if outcome is not None:
            worst = _worst(worst, outcome)

    if missing:
        status = "not_run"
    else:
        status = "passed" if worst == "passed" else "failed"

    result: dict[str, object] = {
        "status": status,
        "requirements": list(CLAIMS[claim]),
        "node_ids": list(nodeids),
    }
    if missing:
        result["missing_node_ids"] = missing
    return result


def results_for_mode(mode: str, junit_paths: list[Path]) -> dict[str, dict[str, object]]:
    """Every claim this mode is responsible for, judged against its artifacts."""
    outcomes = junit_outcomes(junit_paths)
    return {claim: claim_result(claim, outcomes) for claim in claims_for_mode(mode)}
