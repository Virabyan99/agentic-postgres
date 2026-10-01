"""`docs/change-governance.md` says what the programs say (ADR 0243, D1484).

The page quotes sentences an operator will meet on a terminal -- the host
gate's four refusals, the status line's forms, the approval's two-name
refusal, the records' note -- and a quoted sentence a program stopped agreeing
with is the class D1484 names. So each is read from the constant the program
raises or prints, never retyped here, and the page must carry it verbatim.
"""

from __future__ import annotations

import pytest

from agentic_postgres import REPO_ROOT, migrations, proposal

pytestmark = [pytest.mark.contract, pytest.mark.p0]

PAGE = REPO_ROOT / "docs" / "change-governance.md"

#: ADR 0243's reach, the sentence every page repeats.
REACH = (
    "they stop an\nunreviewed or altered set reaching a host; they do not authenticate a\nreviewer."
)


@pytest.fixture(scope="module")
def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """Whitespace folded, so a sentence wrapped across lines still matches."""
    return " ".join(text.split())


def test_the_page_quotes_the_four_gate_sentences(page: str) -> None:
    """Each sentence `proposal.gate` raises, exactly; the first with its
    placeholder as the page writes it."""
    flat = _flat(page)
    assert f"`{proposal.GATE_NO_PROPOSAL.format(digest16='<digest16>')}`" in flat
    for sentence in (
        proposal.GATE_OTHER_SET,
        proposal.GATE_NO_APPROVAL,
        proposal.GATE_BAD_APPROVAL,
    ):
        assert f"`{sentence}`" in flat, f"the page does not quote {sentence!r}"


def test_the_page_quotes_the_records_note_and_the_two_name_refusal(page: str) -> None:
    flat = _flat(page)
    assert proposal.NOTE in flat
    assert proposal.SECOND_NAME in flat
    assert _flat(REACH) in flat, "ADR 0243's reach sentence is not on the page"


def test_the_status_lines_the_page_shows_are_the_ones_status_prints(page: str, tmp_path) -> None:
    """The page's status forms, produced by `proposal.status_line` itself over
    a tmp root: not needed, absent, present under 0, the unread reading."""
    digest = "35245421404e77d3" + "0" * 48
    lines = {
        proposal.status_line(tmp_path, digest, (), 1),
        proposal.status_line(tmp_path, digest, ("20261001120004",), 1),
        proposal.status_line(tmp_path, digest, None, 1, unread="<why>"),
    }
    for line in lines:
        assert f"migrate: {line}" in page, f"the page does not show {line!r}"
    assert "present, approved by " in page
    assert "present (approvals_required is 0)" in page
    assert "present; up refuses: " in page
    assert "proposal: not applicable (this project applies no set of its own)" in page


def test_the_page_names_every_destructive_kind_it_counts(page: str) -> None:
    """The page says sixteen; the reader holds sixteen."""
    assert len(migrations.DESTRUCTIVE_KINDS) == 16
    assert "Sixteen kinds" in page


def test_the_page_is_inside_both_documentation_scans_and_indexed() -> None:
    """D1881: a page the walk may be sent to is read by both halves."""
    from tests.contract.test_session12_documented_path import CURRENT_PATH_DOCUMENTS

    from agentic_postgres import dx_record

    for name in ("docs/change-governance.md", "docs/workflows.md", "docs/connectors.md"):
        assert name in dx_record.DOCUMENT_ROOTS, name
        assert name in CURRENT_PATH_DOCUMENTS, name
    index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "(change-governance.md)" in index
