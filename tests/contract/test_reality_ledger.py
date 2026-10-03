"""The Reality Ledger is a program's input (`LEDGER-001`, ADR 0247).

`docs/reality-ledger.yaml` says what each product concept is today. These are
the guard's halves that have a subject now (D2000): the file validates; every
`available` or `beta` row names evidence, every name is a claim or an envelope
subject, and -- where the checkout holds an evidence document (D2021) -- each
passed in the newest one, `today_evidence` included; a concept a customer
cannot reach carries no control; no customer sentence uses a specification §59
word; the rendered page is current. The halves without a subject -- every
console control and every `/api/v1` operation type maps to a row -- are
asserted empty, so the day either set appears this module fails and names the
session that must write the real guard.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, reality_ledger

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
    so a status added in one place and not the other is refused here."""
    reality_ledger.validate(ledger)
    schema = json.loads(reality_ledger.SCHEMA_PATH.read_text(encoding="utf-8"))
    enum = schema["$defs"]["row"]["properties"]["status"]["enum"]
    assert tuple(enum) == reality_ledger.STATUSES


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


def test_the_sets_the_guard_will_read_are_empty_today() -> None:
    """The halves of ADR 0247's guard with no subject yet (D2000).

    Every `/api/v1` operation type and every console control must map to a
    ledger row. Neither exists: Session 37 writes the operation types (in
    `src/agentic_postgres/operations.py`) and Session 42 the console (under
    `services/console/`). **Those sessions replace this test with the real
    guard** -- every type and every control names a row whose status is
    `available` or `beta`. Until then the sets are asserted empty, so the day
    one appears this fails rather than passing over a set nobody reads.
    """
    assert not (REPO_ROOT / "src" / "agentic_postgres" / "operations.py").exists(), (
        "operations.py exists: Session 37's guard (every operation type maps to a "
        "ledger row) must replace this assertion"
    )
    assert not (REPO_ROOT / "services" / "console").exists(), (
        "services/console exists: Session 42's guard (every console control maps "
        "to a ledger row) must replace this assertion"
    )
