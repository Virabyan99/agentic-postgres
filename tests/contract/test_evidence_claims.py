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

from agentic_postgres import REPO_ROOT
from agentic_postgres import evidence_claims as claims

pytestmark = [pytest.mark.contract, pytest.mark.p0]

WRITER = REPO_ROOT / "bin" / "write-session-evidence.py"

#: The exact expression the Session 2 plan's Run 8 runs against the merged
#: document. Quoted rather than paraphrased: this is the consumer, and a claim
#: renamed without renaming it here is the defect ADR 0025 records.
PLAN_JQ_EXPRESSION = '.tests.secret_leakage=="passed" and .tests.isolation=="passed"'

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


def test_every_claim_names_registered_requirements() -> None:
    for claim in claims.CLAIMS:
        assert claims.claim_nodeids(claim), f"{claim} resolves to no test"


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
    measured = {mode: claims.claims_for_mode(mode) for mode in claims.MODE_MARKERS}
    assert any(measured.values()), f"no claim is measured anywhere: {measured}"


def test_a_mode_that_carries_a_claim_has_a_static_proof_to_run() -> None:
    """A scan over an empty set proves nothing and passes forever.

    Emptiness is legitimate for a mode with no claim; it is not legitimate for
    one that has claims, because those claims would be permanently ``not_run``.
    """
    for mode in claims.MODE_MARKERS:
        static = claims.static_nodeids_for_mode(mode)
        if not claims.claims_for_mode(mode):
            assert not static, f"{mode} carries no claim but resolved proofs {static}"
            continue
        assert static, f"{mode} has no environment-free claim proof"
        for nodeid in static:
            assert not claims.environment_markers(nodeid)


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


def test_a_skip_is_not_a_pass(tmp_path: Path) -> None:
    """``requires_environment`` skips are how these tests behave in a checkout.

    Correct there, and worthless as evidence. Counting a skip as a pass would
    make a full evidence run producible from a laptop.
    """
    outcomes = all_passing("isolation")
    outcomes[next(iter(outcomes))] = "skipped"
    artifact = write_junit(tmp_path / "tests.xml", outcomes)
    assert claims.claim_result("isolation", claims.junit_outcomes([artifact]))["status"] == "failed"


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
        (("passed", "skipped"), "failed"),
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


def write_host_half(tmp_path: Path, output: Path, *, skip: str | None = None) -> Path:
    outcomes: dict[str, str] = {}
    for claim in claims.claims_for_mode("host"):
        outcomes |= all_passing(claim)
    if skip is not None:
        outcomes[skip] = "skipped"

    artifact = write_junit(tmp_path / "host-tests.xml", outcomes)
    result = run_writer(
        "--session",
        "2",
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
    for claim in claims.claims_for_mode("external"):
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
    assert set(host["tests"]) == set(claims.claims_for_mode("host"))


def test_a_half_carries_its_suite_counts(tmp_path: Path) -> None:
    host = json.loads(write_host_half(tmp_path, tmp_path / "host.json").read_text(encoding="utf-8"))
    assert host["suites"]["host"]["failed"] == 0
    assert host["suites"]["host"]["passed"] > 0


def test_a_half_refuses_when_a_claim_is_not_proved(tmp_path: Path) -> None:
    skipped = claims.claim_nodeids("isolation")[0]
    output = tmp_path / "host.json"
    outcomes: dict[str, str] = {}
    for claim in claims.claims_for_mode("host"):
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
    assert set(document["tests"]) == set(claims.CLAIMS)
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
    for claim in claims.CLAIMS:
        assert claim in result.stderr
    assert not (tmp_path / "session-02.json").exists()


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
