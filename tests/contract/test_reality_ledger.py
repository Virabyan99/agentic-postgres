"""The Reality Ledger is a program's input (`LEDGER-001`, ADR 0247).

`docs/reality-ledger.yaml` says what each product concept is today. These are
the guard's halves that have a subject now (D2000): the file validates; every
`available` or `beta` row names evidence, every name is a claim or an envelope
subject, and -- where the checkout holds an evidence document (D2021) -- each
passed in the newest one, `today_evidence` included; a concept a customer
cannot reach carries no control; no customer sentence uses a specification §59
word; the rendered page is current; and since Session 37 (ADR 0254) every
`/api/v1` operation type names a row, accepted exactly when that row is
`available` or `beta` -- or, since Session 38 (ADR 0261), `trial`: reachable
while its evidence is collected, and held by three rules to the session that
introduced its claims. The half without a subject -- every console control
maps to a row -- is asserted empty, so the day the console appears this module
fails and names the session that must write the real guard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, operations, reality_ledger

pytestmark = [pytest.mark.contract, pytest.mark.p0]

RENDERER = REPO_ROOT / "bin" / "render-reality-ledger.py"

#: The substrate the operator runs today. Each row must carry a claim that
#: passed, or the evidence test below would pass over rows that name nothing.
SUBSTRATE = (
    "postgresql",
    "project_isolation",
    "backups_and_pitr",
    "agents",
    "workflows",
    "connectors",
    "audit",
)


@pytest.fixture(scope="module")
def ledger() -> dict:
    return reality_ledger.load()


def test_the_ledger_validates(ledger: dict) -> None:
    """The schema, the unique ids, and the module's statuses ARE the schema's,
    so a status added in one place and not the other is refused here -- six
    since ADR 0261 added `trial`, written out so a seventh is added on purpose."""
    reality_ledger.validate(ledger)
    schema = json.loads(reality_ledger.SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["$defs"]["row"]["properties"]["status"]["enum"]
    assert tuple(enum) == reality_ledger.STATUSES
    assert reality_ledger.STATUSES == (
        "available",
        "beta",
        "trial",
        "planned",
        "not_metered",
        "not_offered",
    )
    assert reality_ledger.REACHABLE == operations.ACCEPTING_STATUSES


def test_every_evidence_name_is_a_claim_or_an_envelope_subject(ledger: dict) -> None:
    """The half every checkout can read, CI's included (D2021): `evidence` is
    non-empty exactly for `available`/`beta`, and every name in `evidence` and
    `today_evidence` is a claim in `CLAIMS` or a `capacity.ENVELOPE` subject."""
    problems = reality_ledger.evidence_problems(ledger, None)
    assert not problems, problems
    by_id = {row["id"]: row for row in ledger["rows"]}
    unproved = [name for name in SUBSTRATE if by_id[name]["today_evidence"] is None]
    assert not unproved, f"substrate rows with no today_evidence: {unproved}"


def test_available_and_beta_rows_name_evidence_that_resolves(ledger: dict) -> None:
    """Read against the NEWEST `evidence/session-NN.json`. A claim that was
    `not_run` or `failed` there is not evidence, and a status the evidence
    cannot back is the surface claiming what the node does not do.

    `evidence/*` is gitignored (runbook §6.1), so a checkout with no evidence
    document cannot read this half and SKIPS saying so (D2021) -- the third
    outcome, reported. The workstation and the host, where the session gates
    run, hold the documents."""
    newest = reality_ledger.newest_evidence()
    if newest is None:
        pytest.skip("no evidence/session-NN.json in this checkout (evidence/* is gitignored)")
    path, evidence = newest
    problems = reality_ledger.evidence_problems(ledger, evidence)
    assert not problems, f"against {path.name}: {problems}"


def test_a_claim_that_did_not_pass_is_not_evidence() -> None:
    """ADR 0195: `not_run` and `failed` are reported, never folded into
    `passed`. The ledger names only passed claims today, so without this the
    resolver's status check would be read by nothing."""
    name = "isolation_matrix"
    for status in ("not_run", "failed"):
        evidence = {"claims": {name: {"status": status}}}
        assert not reality_ledger.resolves(name, evidence), status
    assert reality_ledger.resolves(name, {"claims": {name: {"status": "passed"}}})
    assert not reality_ledger.resolves(
        "no_such_claim", {"claims": {"no_such_claim": {"status": "passed"}}}
    )


def test_the_newest_evidence_is_chosen_by_session_number(tmp_path: Path) -> None:
    """`session-9` sorts after `session-10` as text; the reader orders by the
    number, and ignores the per-mode halves (`session-10-host.json`)."""
    for name, marker in (
        ("session-9.json", "nine"),
        ("session-10.json", "ten"),
        ("session-11-host.json", "half"),
    ):
        (tmp_path / name).write_text(json.dumps({"marker": marker}), encoding="utf-8")
    assert reality_ledger.newest_evidence(tmp_path / "absent") is None
    newest = reality_ledger.newest_evidence(tmp_path)
    assert newest is not None
    path, document = newest
    assert (path.name, document["marker"]) == ("session-10.json", "ten")


def test_a_planned_row_has_no_control(ledger: dict) -> None:
    """The fake-complete guard: nothing a customer can press acts on a concept
    that is `planned`, `not_metered` or `not_offered`."""
    assert reality_ledger.unreachable_rows_with_controls(ledger) == []


def test_a_trial_row_is_bounded_to_the_session_that_introduced_its_claims(ledger: dict) -> None:
    """ADR 0261's three rules on the committed ledger: every `trial` row names
    only claims `CLAIM_INTRODUCED_IN` dates to `CURRENT_SESSION`, targets the
    current session, and tells the customer the concept is being verified. A
    row Session 38's close leaves at `trial` fails this the moment the constant
    moves to 39 -- which is how a session cannot leave one behind."""
    from tests.contract.test_evidence_claims import CLAIM_INTRODUCED_IN

    problems = reality_ledger.trial_problems(ledger, CLAIM_INTRODUCED_IN, CURRENT_SESSION)
    assert problems == [], problems


def _trial_row(**changes: object) -> dict:
    row = {
        "id": "planted",
        "concept": "Planted",
        "status": "trial",
        "customer_text": "Open while it is being verified.",
        "today": "Planted.",
        "today_evidence": None,
        "evidence": ["new_claim"],
        "stage5_reality": "Planted.",
        "eventual": "Planted.",
        "controls": [],
        "since_session": 38,
        "target_session": 38,
    }
    row.update(changes)
    return row


def test_the_trial_rules_refuse_each_way_a_row_could_outlive_its_session() -> None:
    """Each rule, broken alone, is refused naming the row; the control -- the
    same row unbroken -- is not. The read at Session 39 is the close that
    forgot: the row did not change, the session did. And the passed half skips
    ONLY a trial row's own `evidence`: the same unpassed claim under `beta` is
    still refused, so `beta` was not loosened (ADR 0261 item 4)."""
    introduced = {"new_claim": 38, "old_claim": 37}

    def problems(row: dict, session: int = 38) -> list[str]:
        return reality_ledger.trial_problems({"rows": [row]}, introduced, session)

    assert problems(_trial_row()) == []
    assert "old_claim" in " ".join(problems(_trial_row(evidence=["new_claim", "old_claim"])))
    assert "not introduced" in " ".join(problems(_trial_row(evidence=["an_envelope_subject"])))
    assert "target_session" in " ".join(problems(_trial_row(target_session=39)))
    assert "target_session" in " ".join(problems(_trial_row(), session=39))
    assert "being verified" in " ".join(problems(_trial_row(customer_text="Open.")))
    # Not a trial row: none of the three rules is its business.
    assert problems(_trial_row(status="beta", evidence=["old_claim"], target_session=30)) == []

    unpassed = {"claims": {"control_set": {"status": "not_run"}}}
    trial = {"rows": [_trial_row(evidence=["control_set"])]}
    beta = {"rows": [_trial_row(status="beta", evidence=["control_set"])]}
    assert reality_ledger.evidence_problems(trial, unpassed) == []
    assert reality_ledger.evidence_problems(beta, unpassed) == [
        "planted: evidence 'control_set' did not pass"
    ]


def test_no_customer_text_uses_a_forbidden_word(ledger: dict) -> None:
    """The §59 words, in the only text written for a customer today. The
    `autoscaling`, `high_availability` and `multi_region` rows say what is not
    offered without using the words -- which is the point of the list."""
    assert reality_ledger.forbidden_words_in(ledger) == []


def test_the_page_is_current() -> None:
    """`--check`, run -- not "the file exists"."""
    result = subprocess.run(
        [sys.executable, str(RENDERER), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_every_operation_type_names_a_ledger_row_and_is_accepted_iff_its_row_is_reachable(
    ledger: dict,
) -> None:
    """ADR 0247's guard for the operation types, real since Session 37 (ADR 0254).

    Every type names a ledger row that exists; the types the control mode
    accepts (`ACCEPTED_TYPES`, in the service) are EXACTLY those whose row is
    `available`, `beta` or -- since ADR 0261 -- `trial`: a row moved without the
    service following, or a type accepted while its row is planned, fails here;
    and the control set's CHECK lists the same types, so the database holds no
    type the table lacks. Session 37 accepted nothing; Session 38's Run 10 moved
    the six executed types' rows to `trial` (D2170), and the five others stay
    refused because their rows stay `planned`.
    """
    rows = {row["id"] for row in ledger["rows"]}
    missing = {t: r for t, r in operations.OPERATION_TYPES.items() if r not in rows}
    assert not missing, f"operation types naming no ledger row: {missing}"

    by_ledger = {t for t in operations.OPERATION_TYPES if operations.accepted(t, ledger)}
    assert set(operations.ACCEPTED_TYPES) == by_ledger, (
        f"the service accepts {sorted(operations.ACCEPTED_TYPES)} and the ledger permits "
        f"{sorted(by_ledger)}: one moved without the other"
    )

    template = (
        REPO_ROOT
        / "projects"
        / "control"
        / "migrations"
        / "templates"
        / "0003-control-registry.sql"
    ).read_text(encoding="utf-8")
    checked = template.split("CHECK (type IN (", 1)[1].split("))", 1)[0]
    assert {name.strip().strip("'") for name in checked.split(",")} == set(
        operations.OPERATION_TYPES
    )


def test_no_console_exists_yet() -> None:
    """The console half of ADR 0247's guard, with no subject yet (D2000).

    Every console control must map to a ledger row; no console exists until
    Session 42 (under `services/console/`), which replaces this test with the
    real guard. Until then the set is asserted empty, so the day it appears
    this fails rather than passing over a set nobody reads. (The operation-type
    half became a guard of its own in Session 37, above.)
    """
    assert not (REPO_ROOT / "services" / "console").exists(), (
        "services/console exists: Session 42's guard (every console control maps "
        "to a ledger row) must replace this assertion"
    )
