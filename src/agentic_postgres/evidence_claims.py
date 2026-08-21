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
#: A ``public_boundary`` claim over ``SEC-NET-001`` was written and removed: that
#: requirement's proofs include an IPv6 scan, the deployment host holds a global
#: IPv6 address, and no network available to run the external gate from has IPv6
#: transit. The claim could only ever come out ``failed`` — not because the
#: boundary is open but because nobody can look at it from here — and a claim
#: that cannot pass is a blocker invented by the evidence writer. The gap is
#: recorded as a divergence and in ``docs/host-baseline.md`` instead, which is
#: what an unmeasured surface deserves. Both modes stay implemented, so the day
#: a scan can be run from an IPv6 network the claim is three lines.
#:
#: Session 3 adds four. Not every Session 3 requirement is a claim, and the
#: reason is structural rather than editorial: a claim needs at least one proof
#: that runs against a deployment (see ``claim_mode``), and ``DBX-MIG-002`` and
#: ``DBX-MIG-003`` are about render determinism and preflight refusal — both
#: entirely properties of a checkout. They are proved, and they appear in the
#: acceptance matrix; they are not guarantees about a running system, so this
#: session's evidence does not name them as ones.
#:
#: Session 4 adds five, and two of them differ from the shape its plan drafted
#: (ADR 0045).
#:
#: ``direct_transport`` was drafted as ``DBX-001, DBX-003, DBX-005,
#: SEC-DBX-001`` — and ``claim_mode`` refuses it, correctly. The first two are
#: proved on the host by running Prisma Migrate and ``psql``; the last two are
#: proved from *off-host*, by failing to reach the same endpoint. One claim, two
#: environments, and neither half of the evidence could report a verdict on it.
#: So the guarantee is split where the measurement is: ``direct_transport`` is
#: "the direct endpoint works for the tools that need it" and
#: ``transport_boundary`` is "neither transport is reachable from outside".
#: ``transport_boundary`` is also the external claim ``public_boundary`` could
#: not be: its proofs scan IPv4 only, so unlike ``SEC-NET-001``'s it can pass
#: from a network with no IPv6 transit.
#:
#: ``transport_isolation`` is separate from ``database_isolation`` for a reason
#: that only appears when you follow the mechanism through. The plan says
#: ``database_isolation`` *gains* ``DEP-ISO-004``; ``claim_session`` is the max
#: of its requirements' sessions, so gaining a Session 4 requirement would move
#: the whole claim to Session 4 — and ``claims_through_session(3)`` would then
#: stop returning it. Session 3's gate would quietly stop recording a claim it
#: has been recording, and the jq expression its operator guide documents would
#: fail against freshly written evidence. Cumulative was meant to mean a later
#: session keeps proving an earlier one's guarantees, not that a later
#: requirement withdraws one from the earlier session's evidence.
CLAIMS: dict[str, tuple[str, ...]] = {
    "isolation": ("DEP-ISO-002",),
    "secret_leakage": ("SEC-SECRET-001", "SEC-SECRET-002"),
    "least_privilege": ("SEC-DB-001", "SEC-DB-002", "DBX-MIG-001"),
    "row_level_security": (
        "SEC-RLS-001",
        "SEC-VIEW-001",
        "SEC-FUNC-001",
        "SEC-DEFAULT-001",
        "SEC-OWNER-001",
    ),
    "database_isolation": ("DEP-ISO-003", "DBX-PG-003"),
    "boot_convergence": ("DEP-BOOT-001",),
    "pooled_transport": ("DBX-002", "DBX-POOL-001", "DBX-POOL-002", "DBX-POOL-003"),
    "direct_transport": ("DBX-001", "DBX-003"),
    "transport_boundary": ("DBX-005", "SEC-DBX-001"),
    "connection_tooling": ("DX-DB-001", "DX-DB-002"),
    "transport_isolation": ("DEP-ISO-004",),
    # Session 5 adds seven, and adds nothing to an existing claim.
    #
    # That is a decision rather than an oversight, and it is the paragraph above
    # applied a second time. `claim_session` is the maximum of a claim's
    # requirements' sessions, so giving `connection_tooling` a Session 5
    # requirement would move the whole claim to Session 5 and **withdraw it from
    # Session 4's evidence** -- and the jq expression
    # `docs/session-04-operator-guide.md` documents would fail against freshly
    # written Session 4 evidence with the product's behaviour unchanged. The
    # same applies to `database_isolation` and `transport_boundary`. Extending a
    # claim is right when the guarantee genuinely grew and wrong when a new
    # requirement merely neighbours an old one (D119).
    #
    # `api_authorization` and `public_api_boundary` are split for the reason
    # `direct_transport` and `transport_boundary` are. `SEC-DOCS-001` is proved
    # on the host, by reading where the credential was materialized and what the
    # containers hold; `SEC-API-001` is proved from off-host, by failing to
    # reach anything. One claim over both could be measured by neither half.
    "rest_surface": (
        "API-SCHEMA-001",
        "API-REST-001",
        "API-RPC-001",
        "API-ERR-001",
        "API-LIMIT-001",
    ),
    "api_contract": ("API-CONTRACT-001", "API-CACHE-001"),
    "api_authorization": ("SEC-ANON-001", "SEC-PRIV-001", "SEC-ROLE-001", "SEC-DOCS-001"),
    "bootstrap_identity": ("SEC-BOOT-001",),
    "api_isolation": ("DEP-ISO-005",),
    "api_tooling": ("DX-API-001",),
    "public_api_boundary": ("SEC-API-001",),
    # Session 6 adds seven, and every one of them names requirement IDs targeted
    # at Session 6. That sounds like a restatement of the obvious and is the
    # decision ADR 0089 records, because the plan's own §7 table did not.
    #
    # Three of the six IDs §2 introduced as "new" already existed:
    # `SEC-BOOT-001` (Session 5), `SEC-REV-001` (Session 9) and `DEP-ISO-003`
    # (Session 3). Prefix validity was checked; the directory was not. Taking
    # them literally was measured, and neither failure is loud:
    #
    #   `project_isolation: ("DEP-ISO-003",)` resolves to claim_session=3, so
    #   the Session 3, 4 and 5 gates each gain a claim whose proofs are Session
    #   6 auth tests. Run through the real `merge`, Session 3's evidence goes
    #   from exit 0 / `passed` to exit 5 / `failed` -- and the failing document
    #   is still written, so nobody gets an error to investigate.
    #
    #   `token_non_resurrection: ("SEC-REV-001",)` resolves to claim_session=9.
    #   `claims_for_mode("host", 6)` simply does not contain it. No error, no
    #   warning, no entry: the property §2 calls the session's sharpest would
    #   have been absent from the evidence and the gate would have exited 0.
    #
    # So the three are `DEP-ISO-006`, `SEC-REV-002` and `SEC-BOOT-002`.
    # `SEC-BOOT-002` is also a meaning split rather than only a session one:
    # `SEC-BOOT-001` is that the temporary bootstrap *issuer* holds the only
    # private key, and Session 6's property is that the first *administrator* is
    # created locally and exactly once. One ID for two guarantees is what D47
    # refused, read backwards.
    #
    # `admin_authorization` pairs API-ADMIN-001 with SEC-BOOT-002 because the
    # scope check is only meaningful while administrator creation is not an HTTP
    # capability -- an endpoint that mints administrators makes every scope
    # check decorative.
    #
    # `key_ownership` carries SEC-KEY-002, whose transition is deliberately
    # unexercised this session (ADR 0088). Its live proofs assert the
    # invariants that hold without starting a rotation; the convergence itself
    # is recorded in the run log as unproved rather than claimed here.
    "token_contract": ("SEC-JWT-001", "API-AUTH-002"),
    "key_ownership": ("SEC-KEY-001", "SEC-KEY-002"),
    "credential_storage": ("SEC-CRED-001", "SEC-CRED-002"),
    "identity_endpoints": ("API-AUTH-001",),
    "admin_authorization": ("API-ADMIN-001", "SEC-BOOT-002"),
    "token_non_resurrection": ("SEC-REV-002",),
    "project_isolation": ("DEP-ISO-006",),
    # Session 7 added nothing here in Run 1, and that was a measured constraint
    # rather than an omission (D331).
    #
    # Run 1 wrote `connection_budget_division` and `storage_scope_class` and the
    # model refused both: `claim_mode` raises *"has no live proof: every test it
    # names runs in a checkout, so no deployment is being measured"*. Run 1's
    # guarantees are the connection division and the scope partition, and both
    # are proved entirely offline -- so neither is a claim under ADR 0045, which
    # shapes a claim by where it can be measured. **They are still not here**,
    # for the same reason, and their tests exist and pass as ordinary suite
    # properties.
    #
    # Run 9 adds the nine below, and every one names requirement IDs targeted at
    # Session 7 and only at Session 7 (ADR 0089). That is not a restatement of
    # the obvious: `claim_session` derives from `max()`, so a single older ID
    # mixed in either drags the whole claim into an earlier session's evidence or
    # hides it from this one's gate, and both failures are silent.
    #
    # One claim per guarantee (D47). `object_completion` carries two IDs because
    # "an object becomes available only when the provider has verified it, and
    # only within the bound this deployment published" is one guarantee measured
    # from two sides; `storage_credentials` carries two for the same reason --
    # what the runtimes hold, and what the credential they hold can do.
    #
    # **Every one of these will report `not_run` until a host trip.** All eleven
    # requirements are proved by `live_host` tests that have never executed in
    # any environment, because no deployment has ever started a storage
    # container. D282 is Session 6 writing this sentence one run before its own
    # trip found nine defects, and it is written here for the same reason: a
    # claim that has never been measured must not be mistaken for one that
    # passed.
    "object_ownership": ("STO-OWN-001",),
    "object_keys": ("STO-KEY-001",),
    "presigned_url_containment": ("STO-URL-001",),
    "object_completion": ("STO-COMPLETE-001", "STO-BOUND-001"),
    "tombstone_ordering": ("STO-TOMB-001",),
    "cleanup_convergence": ("STO-CLEAN-001",),
    "storage_authorization": ("STO-AGENT-001",),
    "storage_credentials": ("STO-SECRET-001", "STO-CRED-001"),
    "storage_isolation": ("DEP-ISO-007",),
    # The one Session 7 claim measured from off-host, which is what makes the
    # gate's external mode meaningful for this session rather than ceremonial.
    "public_storage_boundary": ("STO-PUBLIC-001",),
    # Session 8 adds eight, and ADR 0132 is the decision behind their shape.
    #
    # Run 6 replaced five placeholders with CONTRACT tests, which was right --
    # they are contract properties -- and left the session with no claim it could
    # make. Measured before anything was written: every node id the six Session 8
    # requirements named carried no environment marker, and a claim over two of
    # them was refused *"has no live proof: every test it names runs in a
    # checkout"*. The control was `object_ownership`, which resolves to `host`.
    #
    # So four requirements gained live proofs rather than twins -- the guarantee
    # did not change, only where it is measured -- and four new ids carry
    # guarantees that are about a deployment and did not exist offline.
    #
    # `agent_query_construction` carries two ids for the reason
    # `object_completion` does: *no caller input becomes syntax* is ONE guarantee
    # measured from two sides, the builder's and the attacker's.
    #
    # **`AGT-DRIFT-001` is deliberately absent.** Its guarantee is a property of
    # the compiler and is complete in a checkout, so under ADR 0045 it is not a
    # claim. D331 is the precedent and it is exactly this situation: Session 7's
    # Run 1 wrote `connection_budget_division` and `storage_scope_class`, the
    # model refused both, and they stayed out as ordinary suite properties rather
    # than being given a host arm to qualify them.
    #
    # **Every one of these reports `not_run` until a host trip.** No deployment
    # has started an MCP container anywhere. D282 wrote this sentence one run
    # before Session 6's trip found nine defects; a claim that has never been
    # measured must not be mistaken for one that passed.
    "agent_reads": ("AGT-READ-001",),
    "agent_query_construction": ("AGT-SQL-001", "SEC-INJ-001"),
    "agent_scopes": ("AGT-SCOPE-001",),
    "agent_budgets": ("AGT-BUDGET-001",),
    "agent_surface": ("AGT-PLANE-001",),
    "agent_authentication": ("AGT-TOKEN-001",),
    "agent_credentials": ("AGT-CRED-001",),
    # The one measured from off-host, and the reason Session 8's external mode
    # is not ceremonial.
    "public_agent_boundary": ("AGT-PUBLIC-001",),
}

#: Worst-first, so combining two observations of one test is a max().
_SEVERITY = ("failed", "skipped", "passed")


class ClaimError(RuntimeError):
    """A claim cannot be resolved. No verdict is produced for it."""


# ---------------------------------------------------------------------------
# The registry side
# ---------------------------------------------------------------------------


@cache
def _registry() -> dict[str, dict[str, object]]:
    entries = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not entries:
        raise ClaimError(f"{REGISTRY_PATH} is empty")
    return {
        entry["id"]: {
            "nodeids": tuple(entry.get("test_nodeids") or ()),
            "target_session": entry["target_session"],
        }
        for entry in entries
    }


def _requirement(requirement: str) -> dict[str, object]:
    try:
        return _registry()[requirement]
    except KeyError:
        raise ClaimError(f"{requirement} is not in the acceptance registry") from None


def requirement_nodeids(requirement: str) -> tuple[str, ...]:
    nodeids = _requirement(requirement)["nodeids"]
    if not nodeids:
        raise ClaimError(f"{requirement} lists no test node IDs")
    return nodeids  # type: ignore[return-value]


def claim_session(claim: str) -> int:
    """The session a claim belongs to: the latest of its requirements'.

    Derived from the registry rather than declared beside the claim, for the
    same reason ``claim_mode`` is derived from markers: a claim that gains a
    requirement from a later session becomes that session's claim without
    anyone remembering to say so.

    It exists because ``CLAIMS`` is one dictionary and the gates are not.
    Session 2's evidence must not report a verdict on a guarantee Session 2 did
    not make -- and, worse, ``merge`` refuses to write a document that is silent
    about a claim, so a Session 3 claim in the flat set would have made the
    Session 2 merge unsatisfiable by any pair of runs (ADR 0039).
    """
    if claim not in CLAIMS:
        raise ClaimError(f"unknown claim: {claim}")
    return max(int(_requirement(name)["target_session"]) for name in CLAIMS[claim])


def claims_through_session(session: int) -> tuple[str, ...]:
    """Every claim a gate for ``session`` is answerable for, cumulatively.

    Cumulative because the product is: Session 3 does not stop having to keep
    secrets out of its images. The Session 3 gate therefore proves Session 2's
    claims as well, and its evidence records them.
    """
    return tuple(claim for claim in sorted(CLAIMS) if claim_session(claim) <= session)


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


def claims_for_mode(mode: str, session: int) -> tuple[str, ...]:
    """The claims of ``mode`` that a gate for ``session`` is answerable for.

    ``session`` is required rather than defaulted. A default would be a fourth
    place that knows which session is current, and the one thing every caller
    here does know is which session's gate it is.
    """
    if mode not in MODE_MARKERS:
        raise ClaimError(f"unknown mode: {mode}. Expected one of {sorted(MODE_MARKERS)}.")
    return tuple(claim for claim in claims_through_session(session) if claim_mode(claim) == mode)


def static_nodeids_for_mode(mode: str, session: int) -> tuple[str, ...]:
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
    for claim in claims_for_mode(mode, session):
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


def results_for_mode(
    mode: str, session: int, junit_paths: list[Path]
) -> dict[str, dict[str, object]]:
    """Every claim this mode is responsible for, judged against its artifacts."""
    outcomes = junit_outcomes(junit_paths)
    return {claim: claim_result(claim, outcomes) for claim in claims_for_mode(mode, session)}
