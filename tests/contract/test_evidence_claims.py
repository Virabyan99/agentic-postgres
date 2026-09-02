"""Evidence must name what it proved, and must not claim what it did not run.

ADR 0025. The old half-writer emitted ``{"tests": {"host_suite": "passed"}}``,
which is the name of a command rather than of a guarantee, and which no reader
of ``evidence/session-02.json`` could use to answer "did secrets stay in?".

The tests below are about the three ways a claim could be weaker than it looks:
a proof that did not run, a proof that was skipped, and a claim whose proofs
live in an environment this half could not reach. Each has its own status, and
none of them is ``passed``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

WRITER = REPO_ROOT / "bin" / "write-session-evidence.py"

#: The exact expression the Session 2 plan's Run 8 runs against the merged
#: document. Quoted rather than paraphrased: this is the consumer, and a claim
#: renamed without renaming it here is the defect ADR 0025 records.
PLAN_JQ_EXPRESSION = '.tests.secret_leakage=="passed" and .tests.isolation=="passed"'

#: The exact expression the Session 3 plan's Run 9 runs, for the same reason.
SESSION_THREE_JQ_EXPRESSION = (
    '.tests.row_level_security=="passed" and .tests.database_isolation=="passed"'
)

#: The session whose halves the merge fixtures below build. Pinned to 2 rather
#: than to ``CURRENT_SESSION``: those tests exercise the two-environment merge,
#: and Session 3 has one environment (D45). The single-half path is tested
#: separately, at ``CURRENT_SESSION``.
HALF_SESSION = 2

#: The session whose evidence has exactly one half. Pinned to 3 for the same
#: reason ``HALF_SESSION`` is pinned to 2: the test below is *about* a session
#: with one environment, and Session 3 is the one that has one (D45, D78).
#:
#: It read ``CURRENT_SESSION`` until Session 4 restored the external gate (D82),
#: at which point it began asserting that a two-environment session merges from a
#: single half — the exact refusal the test after it exists to prove (ADR 0045).
SINGLE_ENVIRONMENT_SESSION = 3

_BODIES = {
    "passed": "",
    "failed": '<failure message="synthetic">synthetic</failure>',
    "error": '<error message="synthetic">synthetic</error>',
    "skipped": '<skipped message="synthetic" type="pytest.skip"/>',
}


def write_junit(path: Path, outcomes: dict[str, str]) -> Path:
    """A JUnit file recording exactly these node IDs with exactly these results.

    Node IDs may carry a ``[case]`` suffix, so the parametrized path is exercised
    by the same helper rather than by a second one that could drift from it.
    """
    cases = []
    counts = {"failed": 0, "error": 0, "skipped": 0}
    for nodeid, outcome in outcomes.items():
        base, _, parameters = nodeid.partition("[")
        classname, name = claims.junit_key(base)
        if parameters:
            name = f"{name}[{parameters}"
        cases.append(
            f'<testcase classname="{classname}" name="{name}" time="0.0">'
            f"{_BODIES[outcome]}</testcase>"
        )
        if outcome in counts:
            counts[outcome] += 1

    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites><testsuite name="pytest" tests="{len(outcomes)}" '
        f'failures="{counts["failed"]}" errors="{counts["error"]}" '
        f'skipped="{counts["skipped"]}" time="0.0">' + "".join(cases) + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def all_passing(claim: str) -> dict[str, str]:
    return dict.fromkeys(claims.claim_nodeids(claim), "passed")


# ---------------------------------------------------------------------------
# The claim table against the registry and the suite
# ---------------------------------------------------------------------------


def test_the_claims_the_plan_checks_by_name_exist() -> None:
    """The plan's jq expression is the contract; these are its two keys."""
    for key in ("secret_leakage", "isolation"):
        assert f".tests.{key}" in PLAN_JQ_EXPRESSION
        assert key in claims.CLAIMS


def test_the_claims_the_session_three_plan_checks_by_name_exist() -> None:
    for key in ("row_level_security", "database_isolation"):
        assert f".tests.{key}" in SESSION_THREE_JQ_EXPRESSION
        assert key in claims.CLAIMS


def test_every_claim_names_registered_requirements() -> None:
    for claim in claims.CLAIMS:
        assert claims.claim_nodeids(claim), f"{claim} resolves to no test"


# ---------------------------------------------------------------------------
# Which session a claim belongs to (ADR 0039)
# ---------------------------------------------------------------------------


def test_a_claims_session_is_the_latest_of_its_requirements() -> None:
    """Derived from the registry, so a claim cannot lie about when it started."""
    assert claims.claim_session("isolation") == 2
    assert claims.claim_session("secret_leakage") == 2
    for claim in ("least_privilege", "row_level_security", "database_isolation"):
        assert claims.claim_session(claim) == 3, claim


def test_claims_are_cumulative_and_a_later_one_is_not_backdated() -> None:
    """The property that makes one CLAIMS table safe for several gates.

    Session 2's gate must not report a verdict on a guarantee Session 2 does not
    offer -- and ``merge`` refuses to write a document that is silent about a
    claim, so a Session 3 claim visible to Session 2 would have made the Session
    2 merge unsatisfiable by any pair of runs.
    """
    two = set(claims.claims_through_session(2))
    three = set(claims.claims_through_session(3))

    # Checked against the HAND-WRITTEN roster, not against `claim_session`.
    #
    # `CLAIM_INTRODUCED_IN`'s own docstring warns against deriving an expectation
    # from the value under test, and this is not that: the roster is written out
    # by hand and `claims_through_session` is computed from the registry, so this
    # compares two independent sources and disagreeing is the finding.
    #
    # The literal used to be `{"isolation", "secret_leakage"}`, Session 2's whole
    # claim set until Run 6 retrofitted seven more. A snapshot needs editing
    # every time the set grows, which is exactly when somebody edits it without
    # checking that the growth was intended.
    assert two == {name for name, session in CLAIM_INTRODUCED_IN.items() if session <= 2}
    assert three == {name for name, session in CLAIM_INTRODUCED_IN.items() if session <= 3}

    assert {"isolation", "secret_leakage"} <= two, "Session 2's original pair is still there"
    assert two < three, "Session 3 must keep making Session 2's promises"
    assert "database_isolation" in three - two


def test_every_claim_belongs_to_a_session_the_release_has_reached() -> None:
    """A claim owned by a future session would be unprovable and permanently
    absent from the evidence of every session that can run."""
    for claim in claims.CLAIMS:
        session = claims.claim_session(claim)
        assert session <= CURRENT_SESSION, (
            f"{claim} belongs to session {session}, which this release has not reached"
        )


def test_every_claim_node_id_names_a_real_test() -> None:
    """The registry is verified by collection; this catches the reverse drift.

    A node ID the registry lists and no module defines would make the claim
    permanently ``not_run``, which is a correct verdict about an incorrect
    registry — and one nobody would see until an evidence run failed on a host.
    """
    for claim in claims.CLAIMS:
        for nodeid in claims.claim_nodeids(claim):
            claims.environment_markers(nodeid)


def test_every_claim_resolves_to_exactly_one_mode() -> None:
    modes = {claim: claims.claim_mode(claim) for claim in claims.CLAIMS}
    assert set(modes.values()) <= set(claims.MODE_MARKERS)


def test_at_least_one_environment_carries_a_claim() -> None:
    """A table where every claim resolved nowhere would pass every test below.

    Deliberately not "every environment": both of Session 2's claims are proved
    on the host. The external half carries none, for the reason recorded beside
    ``CLAIMS`` — the claim written over ``SEC-NET-001`` could not pass from a
    network with no IPv6 transit, and a claim that cannot pass is an invented
    blocker rather than a measurement.
    """
    measured = {mode: claims.claims_for_mode(mode, CURRENT_SESSION) for mode in claims.MODE_MARKERS}
    assert any(measured.values()), f"no claim is measured anywhere: {measured}"


def test_every_claim_proof_is_collected_by_exactly_one_selector() -> None:
    """The gate runs two selectors per mode; between them they must cover a claim.

    This asserted, until ADR 0045, that a mode carrying a claim resolves at least
    one proof with **no** environment marker. That was true of Sessions 2 and 3 by
    accident — each of their claims happens to include a contract test — and it is
    not the property that matters. Session 4's ``transport_boundary`` and
    ``connection_tooling`` are proved entirely by tests marked ``external``, every
    one of which ``-m external`` collects; nothing is missing from the artifact,
    and the old assertion would have refused a correct claim table.

    The coverage rule it was reaching for: every proof is collected either by the
    mode's own marker or by the explicit node-ID list the gate runs. A proof in
    neither set is one no selector collects, which makes its claim ``not_run``
    forever — and ``not_run`` is a gate failure, so the defect surfaces on a host
    rather than here.
    """
    for mode, marker in claims.MODE_MARKERS.items():
        static = set(claims.static_nodeids_for_mode(mode, CURRENT_SESSION))
        for nodeid in static:
            assert not claims.environment_markers(nodeid), (
                f"{nodeid} carries an environment marker and is also run explicitly"
            )
        for claim in claims.claims_for_mode(mode, CURRENT_SESSION):
            for nodeid in claims.claim_nodeids(claim):
                assert marker in claims.environment_markers(nodeid) or nodeid in static, (
                    f"{claim}'s proof {nodeid} is collected by neither -m {marker} nor "
                    "the explicit node-ID list; the claim would be not_run forever"
                )


def test_a_mode_that_carries_no_claim_resolves_no_proofs() -> None:
    """The half of the assertion above that was measuring something.

    A mode recording no claim must not resolve node IDs to run: the gate would be
    running tests to support a verdict it does not write. Conditional rather than
    universal, and the condition is a real branch — Session 2's external mode
    carried no claim, and Session 4's does.
    """
    for mode in claims.MODE_MARKERS:
        if not claims.claims_for_mode(mode, CURRENT_SESSION):
            static = claims.static_nodeids_for_mode(mode, CURRENT_SESSION)
            assert not static, f"{mode} carries no claim but resolved proofs {static}"


def test_a_claim_spanning_both_environments_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither half could report it, so a verdict would be half-measured."""
    monkeypatch.setitem(claims.CLAIMS, "spanning", ("DEP-ISO-002", "SEC-NET-001"))
    with pytest.raises(claims.ClaimError, match="spans"):
        claims.claim_mode("spanning")


def test_a_claim_with_no_live_proof_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """CFG-001 is proved entirely in a checkout, so it measures no deployment."""
    monkeypatch.setitem(claims.CLAIMS, "checkout_only", ("CFG-001",))
    with pytest.raises(claims.ClaimError, match="no live proof"):
        claims.claim_mode("checkout_only")


def test_an_unregistered_requirement_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(claims.CLAIMS, "invented", ("NO-SUCH-001",))
    with pytest.raises(claims.ClaimError, match="not in the acceptance registry"):
        claims.claim_nodeids("invented")


# ---------------------------------------------------------------------------
# Reading results
# ---------------------------------------------------------------------------


def test_a_complete_passing_artifact_proves_the_claim(tmp_path: Path) -> None:
    artifact = write_junit(tmp_path / "tests.xml", all_passing("isolation"))
    result = claims.claim_result("isolation", claims.junit_outcomes([artifact]))
    assert result["status"] == "passed"
    assert "missing_node_ids" not in result


@pytest.mark.parametrize("outcome", ["failed", "error"])
def test_one_bad_result_fails_the_claim(tmp_path: Path, outcome: str) -> None:
    outcomes = all_passing("isolation")
    outcomes[next(iter(outcomes))] = outcome
    artifact = write_junit(tmp_path / "tests.xml", outcomes)
    assert claims.claim_result("isolation", claims.junit_outcomes([artifact]))["status"] == "failed"


def test_a_skip_is_not_a_pass_and_is_not_a_failure_either(tmp_path: Path) -> None:
    """``requires_environment`` skips are how these tests behave in a checkout.

    Correct there, and worthless as evidence. Counting a skip as a pass would
    make a full evidence run producible from a laptop.

    **This assertion used to be `== "failed"`, and it is replaced by a stricter
    one under ADR 0163.** The concern was right and the assertion over-reached: a
    skip must not be a pass, and `not_run` satisfies that exactly as `failed`
    does — both are non-`passed`, both make the half unproved, both produce exit
    5. What `failed` additionally claimed was that *the system is wrong*, which a
    skip does not say. Session 13's host run published twelve such claims as
    `failed` off 0 test failures (D755).

    Stricter, not weaker: it pins the status, **and** that the claim still blocks,
    **and** that the skipped proof is named — none of which the old assertion
    said.
    """
    outcomes = all_passing("isolation")
    skipped = next(iter(outcomes))
    outcomes[skipped] = "skipped"
    artifact = write_junit(tmp_path / "tests.xml", outcomes)

    result = claims.claim_result("isolation", claims.junit_outcomes([artifact]))
    assert result["status"] == "not_run"
    assert result["status"] != "passed", "a skip must never read as a pass"
    assert result["skipped_node_ids"], "the claim does not name what did not run"


def test_a_real_failure_outranks_a_skip(tmp_path: Path) -> None:
    """ADR 0163. One failure and one skip is `failed`, not `not_run`.

    A skip beside a genuine failure does not soften it, and reporting the pair as
    "the evidence is missing" would bury the half that says the system is wrong.
    """
    outcomes = all_passing("row_level_security")
    keys = list(outcomes)
    assert len(keys) >= 2, "this claim needs two proofs to distinguish the two outcomes"
    outcomes[keys[0]] = "skipped"
    outcomes[keys[1]] = "failed"
    artifact = write_junit(tmp_path / "tests.xml", outcomes)

    result = claims.claim_result("row_level_security", claims.junit_outcomes([artifact]))
    assert result["status"] == "failed"
    assert result["skipped_node_ids"], "the skip is still recorded, it just does not decide"


def test_a_clean_claim_names_nothing_as_unrun(tmp_path: Path) -> None:
    """The control for the two above: neither member appears when all is well.

    Without this, a `claim_result` that always attached both lists would satisfy
    every assertion about them.
    """
    artifact = write_junit(tmp_path / "tests.xml", all_passing("isolation"))
    result = claims.claim_result("isolation", claims.junit_outcomes([artifact]))
    assert result["status"] == "passed"
    assert "skipped_node_ids" not in result
    assert "missing_node_ids" not in result


def test_a_missing_node_id_is_not_run_and_is_named(tmp_path: Path) -> None:
    """Absence is the status that says the evidence is wrong, not the system."""
    outcomes = all_passing("isolation")
    dropped = next(iter(outcomes))
    del outcomes[dropped]
    artifact = write_junit(tmp_path / "tests.xml", outcomes)

    result = claims.claim_result("isolation", claims.junit_outcomes([artifact]))
    assert result["status"] == "not_run"
    assert result["missing_node_ids"] == [dropped]


def test_the_proofs_may_be_split_across_artifacts(tmp_path: Path) -> None:
    """Which is how the gate runs them: one file per pytest invocation."""
    outcomes = all_passing("isolation")
    first = next(iter(outcomes))
    live = write_junit(tmp_path / "live.xml", {first: "passed"})
    rest = write_junit(tmp_path / "static.xml", {k: v for k, v in outcomes.items() if k != first})
    result = claims.claim_result("isolation", claims.junit_outcomes([live, rest]))
    assert result["status"] == "passed"


@pytest.mark.parametrize(
    ("cases", "expected"),
    [
        (("passed", "passed"), "passed"),
        # Worst wins: one open port is not softened by the next one being shut.
        (("failed", "passed"), "failed"),
        # **`not_run`, not `failed`, since ADR 0163.** The collapsing is what is
        # under test here and it is unchanged -- the skip still wins over the
        # pass. What changed is what a claim whose worst outcome is a skip is
        # CALLED: the evidence is missing, not the system wrong (D755).
        (("passed", "skipped"), "not_run"),
        # And a failed case still outranks a skipped one after collapsing.
        (("failed", "skipped"), "failed"),
    ],
)
def test_parameter_cases_collapse_onto_their_node_id(
    tmp_path: Path, cases: tuple[str, str], expected: str
) -> None:
    """The registry says a node ID refers to all of a test's cases.

    ``DEP-ISO-002`` names no parametrized test today, so the cases here are
    synthetic. That is the point: the collapsing must work for whichever
    requirement acquires one, not only for the one that happens to have it.
    """
    outcomes = all_passing("isolation")
    parametrized = next(iter(outcomes))
    del outcomes[parametrized]
    outcomes[f"{parametrized}[first]"] = cases[0]
    outcomes[f"{parametrized}[second]"] = cases[1]

    artifact = write_junit(tmp_path / "tests.xml", outcomes)
    result = claims.claim_result("isolation", claims.junit_outcomes([artifact]))
    assert result["status"] == expected, result


def test_an_empty_artifact_is_refused(tmp_path: Path) -> None:
    """A run that collected nothing must not resolve every claim to not_run.

    It would be a true statement assembled from no measurement at all, and the
    caller has no way to tell it from a run that genuinely lost one test.
    """
    empty = write_junit(tmp_path / "tests.xml", {})
    with pytest.raises(claims.ClaimError, match="no test case"):
        claims.junit_outcomes([empty])


def test_a_missing_artifact_is_refused(tmp_path: Path) -> None:
    with pytest.raises(claims.ClaimError, match="missing"):
        claims.junit_outcomes([tmp_path / "absent.xml"])


# ---------------------------------------------------------------------------
# The writer, end to end
# ---------------------------------------------------------------------------


def deployed(tmp_path: Path, key: str) -> Path:
    path = tmp_path / f"{key}.json"
    path.write_text(
        json.dumps(
            {
                "source_commit": "0" * 40,
                "project": {"key": key, "domain": f"{key}.example.test"},
                "routes": [f"https://{key}.example.test/__apg/healthz"],
                "tls": {"certificate_sha256": "a" * 64},
            }
        ),
        encoding="utf-8",
    )
    return path


def run_writer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRITER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def write_host_half(
    tmp_path: Path, output: Path, *, skip: str | None = None, session: int = HALF_SESSION
) -> Path:
    outcomes: dict[str, str] = {}
    for claim in claims.claims_for_mode("host", session):
        outcomes |= all_passing(claim)
    if skip is not None:
        outcomes[skip] = "skipped"

    artifact = write_junit(tmp_path / "host-tests.xml", outcomes)
    result = run_writer(
        "--session",
        str(session),
        "--mode",
        "host",
        "--project-a-outputs",
        str(deployed(tmp_path, "alpha-dev")),
        "--project-b-outputs",
        str(deployed(tmp_path, "beta-dev")),
        "--junit",
        str(artifact),
        "--output",
        str(output),
    )
    if skip is None:
        assert result.returncode == 0, result.stdout + result.stderr
    return output


#: A real external node ID, so the external half's artifact is not empty. The
#: external mode carries no claim, but it still ran a suite, and an artifact
#: recording nothing is refused.
EXTERNAL_TEST = "tests/external/test_session2_public_edge.py::test_the_scan_can_detect_an_open_port"


def write_external_half(tmp_path: Path, output: Path) -> Path:
    outcomes: dict[str, str] = {EXTERNAL_TEST: "passed"}
    for claim in claims.claims_for_mode("external", HALF_SESSION):
        outcomes |= all_passing(claim)

    artifact = write_junit(tmp_path / "external-tests.xml", outcomes)
    result = run_writer(
        "--session",
        "2",
        "--mode",
        "external",
        "--project-a-outputs",
        str(deployed(tmp_path, "alpha-dev")),
        "--project-b-outputs",
        str(deployed(tmp_path, "beta-dev")),
        "--junit",
        str(artifact),
        "--output",
        str(output),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def test_a_half_records_both_project_keys(tmp_path: Path) -> None:
    """``project_keys`` names the deployment, not the half's own coverage.

    Before ADR 0025 it was ``[project A]`` unconditionally, so the merged
    document of a two-project host could not be told from a one-project one --
    in a session whose headline claim is that two projects stay apart.
    """
    half = json.loads(write_host_half(tmp_path, tmp_path / "host.json").read_text(encoding="utf-8"))
    assert half["project_keys"] == ["alpha-dev", "beta-dev"]


def test_a_half_records_only_the_claims_of_its_own_mode(tmp_path: Path) -> None:
    host = json.loads(write_host_half(tmp_path, tmp_path / "host.json").read_text(encoding="utf-8"))
    assert set(host["tests"]) == set(claims.claims_for_mode("host", HALF_SESSION))


def test_a_half_carries_its_suite_counts(tmp_path: Path) -> None:
    host = json.loads(write_host_half(tmp_path, tmp_path / "host.json").read_text(encoding="utf-8"))
    assert host["suites"]["host"]["failed"] == 0
    assert host["suites"]["host"]["passed"] > 0


def test_a_half_refuses_when_a_claim_is_not_proved(tmp_path: Path) -> None:
    skipped = claims.claim_nodeids("isolation")[0]
    output = tmp_path / "host.json"
    outcomes: dict[str, str] = {}
    for claim in claims.claims_for_mode("host", HALF_SESSION):
        outcomes |= all_passing(claim)
    outcomes[skipped] = "skipped"

    artifact = write_junit(tmp_path / "host-tests.xml", outcomes)
    result = run_writer(
        "--session",
        "2",
        "--mode",
        "host",
        "--project-a-outputs",
        str(deployed(tmp_path, "alpha-dev")),
        "--junit",
        str(artifact),
        "--output",
        str(output),
    )
    assert result.returncode == 5, result.stdout + result.stderr
    assert "isolation" in result.stderr


def test_a_half_requires_a_junit_artifact(tmp_path: Path) -> None:
    result = run_writer(
        "--session",
        "2",
        "--mode",
        "host",
        "--project-a-outputs",
        str(deployed(tmp_path, "alpha-dev")),
        "--output",
        str(tmp_path / "host.json"),
    )
    assert result.returncode == 2
    assert "--junit" in result.stderr


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------


def test_the_merged_document_satisfies_the_plans_check(tmp_path: Path) -> None:
    host = write_host_half(tmp_path, tmp_path / "host.json")
    external = write_external_half(tmp_path, tmp_path / "external.json")
    merged = tmp_path / "session-02.json"

    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(host),
        "--external-input",
        str(external),
        "--output",
        str(merged),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    document = json.loads(merged.read_text(encoding="utf-8"))
    assert document["status"] == "passed"
    for claim in ("secret_leakage", "isolation"):
        assert document["tests"][claim] == "passed", claim
    assert set(document["tests"]) == set(claims.claims_through_session(HALF_SESSION))
    assert set(document["suites"]) == {"host", "external"}


def test_a_claim_neither_half_recorded_stops_the_merge(tmp_path: Path) -> None:
    """The silent case: two halves that both passed, and a claim nobody ran.

    A half with no ``tests`` map is what every Session 2 half looked like before
    ADR 0025, so this is also the regression test for reintroducing the old
    shape by accident.
    """
    host = json.loads(write_host_half(tmp_path, tmp_path / "host.json").read_text(encoding="utf-8"))
    host["tests"] = {}
    host["claims"] = {}
    stripped = tmp_path / "host-stripped.json"
    stripped.write_text(json.dumps(host), encoding="utf-8")

    external = write_external_half(tmp_path, tmp_path / "external.json")
    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(stripped),
        "--external-input",
        str(external),
        "--output",
        str(tmp_path / "session-02.json"),
    )
    assert result.returncode == 5
    for claim in claims.claims_through_session(HALF_SESSION):
        assert claim in result.stderr
    assert not (tmp_path / "session-02.json").exists()


def test_a_session_with_one_environment_merges_a_single_half(tmp_path: Path) -> None:
    """Session 3 has no external gate, so its evidence has one half (D45, D78).

    The merge still runs: it is what computes ``status`` and what refuses a
    document that is silent about a claim. Skipping it and renaming the half
    would produce a session document with no verdict in it.
    """
    session = SINGLE_ENVIRONMENT_SESSION
    assert not claims.claims_for_mode("external", session), (
        f"session {session} has acquired an external claim; this test no longer "
        "describes a session with one environment"
    )

    outcomes: dict[str, str] = {}
    for claim in claims.claims_for_mode("host", session):
        outcomes |= all_passing(claim)
    artifact = write_junit(tmp_path / "host-tests.xml", outcomes)

    half = tmp_path / "session-03-host.json"
    written = run_writer(
        "--session", str(session),
        "--mode", "host",
        "--project-a-outputs", str(deployed(tmp_path, "alpha-dev")),
        "--project-b-outputs", str(deployed(tmp_path, "beta-dev")),
        "--junit", str(artifact),
        "--output", str(half),
    )  # fmt: skip
    assert written.returncode == 0, written.stdout + written.stderr

    merged = tmp_path / "session-03.json"
    result = run_writer(
        "--session", str(session),
        "--host-input", str(half),
        "--output", str(merged),
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr

    document = json.loads(merged.read_text(encoding="utf-8"))
    assert document["status"] == "passed"
    assert document["session"] == session
    assert set(document["tests"]) == set(claims.claims_through_session(session))
    for claim in ("row_level_security", "database_isolation"):
        assert document["tests"][claim] == "passed", claim


def test_a_single_half_is_refused_for_a_session_that_has_an_external_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard that keeps the convenience from becoming a hole.

    Without it, omitting ``--external-input`` for a session whose claims are
    partly measured from outside would produce a document whose ``status`` was
    computed from half the guarantees -- and it would say ``passed``.
    """
    del monkeypatch
    host = write_host_half(tmp_path, tmp_path / "host.json")
    result = run_writer(
        "--session", str(HALF_SESSION),
        "--host-input", str(host),
        "--output", str(tmp_path / "session-02.json"),
    )  # fmt: skip

    if claims.claims_for_mode("external", HALF_SESSION):
        assert result.returncode == 2
        assert "measured from outside" in result.stderr
        assert not (tmp_path / "session-02.json").exists()
    else:
        # Session 2 carries no external claim either, for the SEC-NET-001 reason
        # recorded beside CLAIMS, so the omission is legitimate there too. The
        # branch is kept so that reinstating that claim turns this test back into
        # the refusal it is named for rather than silently passing.
        assert result.returncode == 0, result.stdout + result.stderr


#: The session that restored the external gate (D82). Pinned, like the two
#: constants above, so the refusal below is exercised against a session that
#: really does measure something from off-host.
TWO_ENVIRONMENT_SESSION = 4


def test_a_single_half_is_refused_at_the_session_with_two_environments(tmp_path: Path) -> None:
    """The refusal above, actually run.

    ``test_a_single_half_is_refused_for_a_session_that_has_an_external_claim``
    takes its ``else`` branch for Session 2 and always has: Session 2 carries no
    external claim, for the ``SEC-NET-001`` reason recorded beside ``CLAIMS``. So
    the guard has been asserted about and never exercised. Session 4 carries two
    external claims (ADR 0045), which makes this the first run of it.
    """
    session = TWO_ENVIRONMENT_SESSION
    external = claims.claims_for_mode("external", session)
    assert external, (
        f"session {session} carries no external claim, so this test measures nothing; "
        "the external gate was restored in Session 4 by D82"
    )

    host = write_host_half(tmp_path, tmp_path / "host.json", session=session)
    output = tmp_path / f"session-{session:02d}.json"
    result = run_writer(
        "--session", str(session),
        "--host-input", str(host),
        "--output", str(output),
    )  # fmt: skip

    assert result.returncode == 2, result.stdout + result.stderr
    assert "measured from outside" in result.stderr
    for claim in external:
        assert claim in result.stderr, f"the refusal does not name {claim}"
    assert not output.exists(), "a document was written for a session measured by half"


def test_halves_describing_different_deployments_are_refused(tmp_path: Path) -> None:
    """The pre-existing MUST_AGREE rule, which nothing exercised until now."""
    host = write_host_half(tmp_path, tmp_path / "host.json")
    external_path = write_external_half(tmp_path, tmp_path / "external.json")

    external = json.loads(external_path.read_text(encoding="utf-8"))
    external["source_commit"] = "1" * 40
    external_path.write_text(json.dumps(external), encoding="utf-8")

    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(host),
        "--external-input",
        str(external_path),
        "--output",
        str(tmp_path / "session-02.json"),
    )
    assert result.returncode == 5
    assert "source_commit" in result.stderr
    assert not (tmp_path / "session-02.json").exists()


def test_a_failed_claim_survives_the_merge_as_a_failure(tmp_path: Path) -> None:
    host_path = write_host_half(tmp_path, tmp_path / "host.json")
    host = json.loads(host_path.read_text(encoding="utf-8"))
    host["tests"]["isolation"] = "failed"
    host_path.write_text(json.dumps(host), encoding="utf-8")

    external = write_external_half(tmp_path, tmp_path / "external.json")
    merged = tmp_path / "session-02.json"
    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(host_path),
        "--external-input",
        str(external),
        "--output",
        str(merged),
    )
    assert result.returncode == 5
    assert json.loads(merged.read_text(encoding="utf-8"))["status"] == "failed"


def test_a_not_run_claim_makes_the_document_not_run_and_still_exits_five(
    tmp_path: Path,
) -> None:
    """ADR 0163's amendment, and D758.

    The document's own status was binary until Session 13 Run 11, so a merge over
    "66 passed, 12 not_run, 0 failed" published `status: failed` — the conflation
    the ADR removes per claim, surviving one level up.

    **Two assertions, and the second is the one that matters.** That the word is
    right, and that a proof nobody ran is still a release control nobody may
    proceed past: exit 5, exactly as a failure (D686).
    """
    host_path = write_host_half(tmp_path, tmp_path / "host.json")
    host = json.loads(host_path.read_text(encoding="utf-8"))
    host["tests"]["isolation"] = "not_run"
    host_path.write_text(json.dumps(host), encoding="utf-8")

    external = write_external_half(tmp_path, tmp_path / "external.json")
    merged = tmp_path / "session-02.json"
    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(host_path),
        "--external-input",
        str(external),
        "--output",
        str(merged),
    )

    assert result.returncode == 5, result.stdout + result.stderr
    assert json.loads(merged.read_text(encoding="utf-8"))["status"] == "not_run"
    assert "NOT RUN" in result.stderr
    assert "these FAILED" not in result.stderr, "nothing failed; the message must not say so"


def test_a_failure_outranks_a_not_run_in_the_document_too(tmp_path: Path) -> None:
    """One of each is `failed`. The control for the test above: without it, a
    merge that always said `not_run` would satisfy that one."""
    host_path = write_host_half(tmp_path, tmp_path / "host.json")
    host = json.loads(host_path.read_text(encoding="utf-8"))
    names = sorted(host["tests"])
    assert len(names) >= 2, "this fixture needs two claims to distinguish the two outcomes"
    host["tests"][names[0]] = "not_run"
    host["tests"][names[1]] = "failed"
    host_path.write_text(json.dumps(host), encoding="utf-8")

    external = write_external_half(tmp_path, tmp_path / "external.json")
    merged = tmp_path / "session-02.json"
    result = run_writer(
        "--session",
        "2",
        "--host-input",
        str(host_path),
        "--external-input",
        str(external),
        "--output",
        str(merged),
    )

    assert result.returncode == 5
    assert json.loads(merged.read_text(encoding="utf-8"))["status"] == "failed"
    assert "these FAILED" in result.stderr


# ---------------------------------------------------------------------------
# ADR 0089 — a claim is built from its own session's requirement IDs
# ---------------------------------------------------------------------------
#
# `claim_session` derives a claim's session from its requirements, so building a
# new claim out of an EARLIER session's requirement ID does not extend that
# requirement -- it relocates the claim backwards. Measured before this was
# written: `project_isolation: ("DEP-ISO-003",)` resolves to session 3, and the
# real `merge` then turns Session 3's evidence from exit 0 / `passed` into exit
# 5 / `failed`, writing the failing document anyway.
#
# The reverse is worse because it is silent. `token_non_resurrection:
# ("SEC-REV-001",)` resolves to session 9, `claims_for_mode("host", 6)` simply
# does not contain it, and the Session 6 gate exits 0 having never recorded the
# property §2 of the plan calls the session's sharpest.


#: Claim -> the session that introduced it. Written out rather than derived,
#: which is the whole point: deriving it from `claim_session` would compare the
#: mechanism against itself and pass for every possible registry (D260's second
#: mutation -- a test that computes its expectation from the value under test).
CLAIM_INTRODUCED_IN = {
    "isolation": 2,
    "secret_leakage": 2,
    "least_privilege": 3,
    "row_level_security": 3,
    "database_isolation": 3,
    "boot_convergence": 3,
    "pooled_transport": 4,
    "direct_transport": 4,
    "transport_boundary": 4,
    "connection_tooling": 4,
    "transport_isolation": 4,
    "rest_surface": 5,
    "api_contract": 5,
    "api_authorization": 5,
    "bootstrap_identity": 5,
    "api_isolation": 5,
    "api_tooling": 5,
    "public_api_boundary": 5,
    "token_contract": 6,
    "key_ownership": 6,
    "credential_storage": 6,
    "identity_endpoints": 6,
    "admin_authorization": 6,
    "token_non_resurrection": 6,
    "project_isolation": 6,
    "object_ownership": 7,
    "object_keys": 7,
    "presigned_url_containment": 7,
    "object_completion": 7,
    "tombstone_ordering": 7,
    "cleanup_convergence": 7,
    "storage_authorization": 7,
    "storage_credentials": 7,
    "storage_isolation": 7,
    "public_storage_boundary": 7,
    "agent_reads": 8,
    "agent_query_construction": 8,
    "agent_scopes": 8,
    "agent_budgets": 8,
    "agent_surface": 8,
    "agent_authentication": 8,
    "agent_credentials": 8,
    "public_agent_boundary": 8,
    # Session 9. Five requirements, five claims, and the two audit ones are
    # split because they are different guarantees: what is recorded, and what
    # happens when recording is impossible (ADR 0141's asymmetry).
    "agent_writes": 9,
    "agent_audit_record": 9,
    "agent_audit_fails_closed": 9,
    "agent_revocation": 9,
    "agent_parameter_boundary": 9,
    "point_in_time_recovery": 10,
    "restore_isolation": 10,
    "restore_verification": 10,
    "recovery_evidence": 10,
    "wal_archiving_signal": 10,
    # Session 11. Four claims for five requirements: DEP-001 is deliberately
    # unclaimed (D669) and carries to Session 12 beside DX-001. They could not be
    # registered until CURRENT_SESSION reached 11, which three separate guards
    # insisted on before any of this could be activated (D670, D672).
    "deployment_preflight": 11,
    "deployment_convergence": 11,
    "operational_diagnosis": 11,
    "log_correlation": 11,
    "isolation_matrix": 12,
    "project_removal": 12,
    "documented_path": 12,
    "fresh_host": 12,
    # Session 13 Run 6: D697's retrofit, as far as the model allows. **Dated to
    # the sessions their requirements belong to, not to 13** — Session 2's
    # evidence has never said whether its own host is hardened, and dating these
    # forward would leave that true while looking closed. Measured first: all
    # three sessions already carry claims, so each already runs the claims path
    # in the mode these need.
    # Session 13.
    "release_version": 13,
    "upgrade_compatibility": 13,
    "upgrade_plan": 13,
    "operator_front_door": 13,
    "metrics_surface": 14,
    "alerting": 14,
    "telemetry_redaction": 14,
    "capacity_envelope": 14,
    "document_kinds": 2,
    "provider_convergence": 2,
    "release_immutability": 2,
    "docker_api_boundary": 2,
    "host_baseline": 2,
    "log_redaction": 2,
    "published_ports": 2,
    "database_extensions": 3,
    "driver_round_trip": 4,
    "port_allocation": 4,
    "runtime_role_privilege": 4,
    "pooled_state_reset": 4,
    "credential_rotation_planes": 4,
}


#: Requirements no claim reports on, and **the measured reason for each**.
#:
#: D697 found the gap and priced it as bookkeeping: *"group the 37 into claims."*
#: **Session 13 Run 6 measured that and it is wrong.** Thirteen were grouped; the
#: remaining twenty-four cannot be, for structural reasons rather than clerical
#: ones. They are not unproved — every one has node ids, those tests run in the
#: gate, and the gate is green. What stays true is that the *evidence document*
#: is silent about them.
#:
#: **Twenty-one have no live proof at all.** `claim_mode` raises for a claim
#: whose every node id runs in a checkout: *"no deployment is being measured."*
#: Reporting them would need an offline-only claim — a decision about what a
#: claim IS (ADR 0045/0089), a change to `merge`, and every gate from 1 up
#: gaining claims to report. That is a session's work, not a morning's, and
#: nobody has taken it.
#:
#: **Three have a live proof and still cannot form one**, each for its own
#: reason — recorded at the foot of `evidence_claims.CLAIMS`.
#:
#: This list is a **register, not a permission**, and the guard below still
#: refuses a *new* orphan.
UNCLAIMED_BY_HISTORY = frozenset(
    {
        # -- No live proof: every node id runs in a checkout. ----------------
        #
        # The manifest and the developer surface: properties of parsing, naming,
        # rendering and the developer's own tooling. None describes a running
        # system.
        "CFG-001",
        "CFG-002",
        "CFG-003",
        "CFG-004",
        "CFG-005",
        "CFG-006",
        "CFG-007",
        "CFG-008",
        "CFG-009",
        "CFG-010",
        "CFG-011",
        "CFG-012",
        "CFG-013",
        "CFG-014",
        "CFG-015",
        "DX-002",
        "DX-003",
        # Render determinism, preflight refusal, and the extension inventory a
        # checkout can answer. **The note above `CLAIMS` has said DBX-MIG-002 and
        # DBX-MIG-003 are checkout properties since Session 3** — which D722
        # records nobody having read before counting them as debt.
        "DBX-MIG-002",
        "DBX-MIG-003",
        "DBX-PG-002",
        # Session 8.
        "AGT-DRIFT-001",
        # -- A live proof, and still no claim. Reasons at the foot of CLAIMS. --
        #
        # Tried as `public_boundary` and removed: its proofs include an IPv6 scan
        # no available network can run, so the claim could only ever come out
        # `failed`. And Session 2 carries no external claim today, so adding one
        # would make `--external-input` newly required for every Session 2 merge.
        "SEC-NET-001",
        # Both span `live_host` AND `external`, which `claim_mode` refuses. A
        # claim names requirements rather than node ids, so there is no subset to
        # claim: splitting these means splitting the requirement itself, which
        # renumbers a Session 2 contract.
        "OPS-HEALTH-001",
        "SEC-TLS-001",
    }
)


def test_no_new_requirement_goes_unreported_by_every_claim() -> None:
    """D697. A requirement no claim names is tested and never reported.

    `CLAIMS` was already checked for claims naming unknown requirements. The
    other direction was not checked at all, and **37 of 127 requirements had no
    claim** — a third of the registry, invisible in every evidence document this
    project has produced.

    The gap is not that they are unproved: their node ids run in the gate. It is
    that `evidence/session-NN.json` — the artefact that says what a release
    guarantees — answers nothing about, for example, whether a service port is
    publicly reachable, though five tests answer it.

    **The historical set is grandfathered and enumerated**, because grouping 37
    requirements into claims is a decision per requirement and doing it in bulk
    is how a Session 2 claim ends up dated Session 12 (D696). What this refuses
    is a **new** one: a requirement added from here on must belong to a claim, or
    say in this list why it does not.

    The list is also checked for staleness — an entry that no longer names a
    registered requirement is removed rather than left to accumulate.
    """
    import yaml

    registry = yaml.safe_load(claims.REGISTRY_PATH.read_text(encoding="utf-8"))
    registered = {entry["id"] for entry in registry}
    claimed = {
        requirement for requirements in claims.CLAIMS.values() for requirement in requirements
    }

    orphaned = registered - claimed - UNCLAIMED_BY_HISTORY
    assert not orphaned, (
        f"these requirements belong to no claim, so no evidence document reports them: "
        f"{sorted(orphaned)}. Add each to a claim, or to UNCLAIMED_BY_HISTORY with the "
        "reason it is not reportable"
    )

    stale = UNCLAIMED_BY_HISTORY - registered
    assert not stale, (
        f"UNCLAIMED_BY_HISTORY names requirements the registry no longer has: "
        f"{sorted(stale)}. A debt register that outlives its debt hides the next one"
    )

    # **The third check, and Run 6's battery is what asked for it.** The two
    # above catch a requirement in neither list and an entry naming nothing. A
    # requirement in BOTH -- claimed, and still recorded as unclaimed -- was
    # caught by neither, so retrofitting one into a claim while leaving its
    # register entry behind passed silently. That is the same "debt register
    # that outlives its debt" the assertion above names, on the axis it does not
    # look at.
    settled = UNCLAIMED_BY_HISTORY & claimed
    assert not settled, (
        f"these are named by a claim AND still recorded as unclaimed: {sorted(settled)}. "
        "Remove each from UNCLAIMED_BY_HISTORY; a register that keeps settled debts "
        "stops being readable as a list of what is missing"
    )

    # The control. A registry that read empty would make both assertions above
    # pass while measuring nothing (D374).
    assert len(registered) > 100, (
        f"only {len(registered)} requirements were read; the registry is not being loaded"
    )
    covered = len(registered & claimed)
    assert covered > 80, (
        f"only {covered} requirements are claimed, which is fewer than this release "
        "demonstrably reports on — the claim map is not being read"
    )


def test_every_claim_is_declared_here() -> None:
    """The table above and `CLAIMS` name the same claims.

    Without this the check below is satisfied by deleting a row: a claim absent
    from the table would simply not be checked, which is how a relocated claim
    would slip through the thing written to catch it.
    """
    assert set(CLAIM_INTRODUCED_IN) == set(claims.CLAIMS), (
        "the introduced-in table and CLAIMS disagree: "
        f"only in table {sorted(set(CLAIM_INTRODUCED_IN) - set(claims.CLAIMS))}, "
        f"only in CLAIMS {sorted(set(claims.CLAIMS) - set(CLAIM_INTRODUCED_IN))}"
    )


def test_a_claim_resolves_to_the_session_that_introduced_it() -> None:
    """ADR 0089. A claim built from an earlier session's requirement ID moves.

    The failure this catches is not a naming slip. A Session 6 claim that
    resolved to Session 3 would make the Session 3, 4 and 5 gates each
    answerable for proofs they cannot run, and their evidence would read
    `failed` with the product unchanged.
    """
    misplaced = {
        claim: (introduced, claims.claim_session(claim))
        for claim, introduced in CLAIM_INTRODUCED_IN.items()
        if claims.claim_session(claim) != introduced
    }
    assert not misplaced, (
        "these claims resolve to a session other than the one that introduced them "
        f"(claim, introduced, resolves to): {sorted(misplaced.items())}. "
        "A claim's session is the MAX of its requirements' target sessions, so this "
        "means a requirement from another session was named (ADR 0089)."
    )


def test_a_session_six_claim_is_not_answerable_by_an_earlier_gate() -> None:
    """The consequence, stated as the thing an operator would actually notice.

    Asserted separately from the session comparison above because it is a
    different failure: a claim could resolve to the right session and still leak
    if `claims_through_session` changed underneath it.
    """
    session_six = {claim for claim, n in CLAIM_INTRODUCED_IN.items() if n == 6}
    for earlier in (2, 3, 4, 5):
        leaked = sorted(session_six & set(claims.claims_through_session(earlier)))
        assert not leaked, (
            f"the session {earlier} gate is answerable for {leaked}, whose proofs are "
            "Session 6 tests it has no way to run. Its evidence would report them "
            "`not_run`, which the writer turns into a failed document"
        )


def test_no_requirement_is_named_by_two_claims() -> None:
    """The half of ADR 0089 the session comparison above cannot see.

    **The mutation battery found this test missing.** Rewriting
    `admin_authorization` to `("API-ADMIN-001", "SEC-BOOT-001")` -- reusing
    Session 5's requirement, which is one of the three mistakes ADR 0089 is
    about -- left `test_a_claim_resolves_to_the_session_that_introduced_it`
    green, because `claim_session` is a `max()` and `max(6, 5)` is still 6.

    So the session check catches a claim built *entirely* from older
    requirements and is blind to an older requirement *added alongside* a
    current one. That second shape is the more likely mistake and the one with
    the worse failure: `SEC-BOOT-001` means "the temporary bootstrap ISSUER
    holds the only private key", and pressing it into a claim about
    administrator creation gives one ID two guarantees, which is what D47
    refused.

    The invariant is that a requirement belongs to at most one claim. Measured
    before it was asserted: no requirement is shared today, across twenty-five
    claims and five sessions. It is not a law of nature -- a future session
    whose guarantee genuinely rests on an earlier requirement's proofs would
    need to relax it, and that is what an ADR is for. What it is not is an
    accident: two claims resting on one set of proofs makes one claim's verdict
    a function of the other's, which is the coupling `claim_session` already
    refuses across sessions.
    """
    owners: dict[str, list[str]] = {}
    for claim, requirements in claims.CLAIMS.items():
        for requirement in requirements:
            owners.setdefault(requirement, []).append(claim)

    shared = {requirement: sorted(names) for requirement, names in owners.items() if len(names) > 1}
    assert not shared, (
        "these requirements are named by more than one claim: "
        f"{shared}. Two claims resting on one set of proofs makes one claim's verdict a "
        "function of the other's, and when the claims belong to different sessions it "
        "also gives one requirement ID two guarantees (ADR 0089)."
    )
