"""`REL-STAGE-001`'s offline half (Session 25 Run 5).

The release names itself in three places and they can drift apart. `VERSION`
at the repository root is the file every rendered document's
`template_version` is read from; `CURRENT_SESSION` is the ordinal the evidence
model is keyed to; and the paragraph of comment above `CURRENT_SESSION` is
where the release SAYS what it is -- which session it moves to, which version
`VERSION` moves to with it, and which ADR 0162 class it proposes for the
upgrade. Until this module the third had no reader at all, which is the shape
D816, D929 and D1247 each name: a declared field nothing reads is an
unverified field, and a release's own account of itself is exactly that kind
of field.

**There is no `agentic_postgres.VERSION` constant, and the plan's §2 assumed
one** (D1346). There is deliberately not one: `VERSION` the file is the single
authority and `template_version()` reads it, which is ADR 0002's rule applied
to the release identity. So the pair this module proves is not *file against
constant* -- that comparison is a tautology, and a tautology is the least
useful thing a proof can be -- but *file and constant against the paragraph
that claims to describe them*. That pair is two authorities and it drifts:
Session 19 moved `VERSION` without moving `CURRENT_SESSION` and the comment is
the only place the two are reconciled for a reader.

The class matters beyond tidiness. Run 7's `upgrade plan` on the host prices
the release, and the plan's §9 makes a `major` there a stop condition. The
number a stop condition is compared against has to be written down somewhere a
proof can read, or the stop is a judgement made at the terminal.

**Marked, and the marks are load-bearing** (D1240).
"""

from __future__ import annotations

import re

import pytest

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, template_version

pytestmark = [pytest.mark.contract, pytest.mark.p0]

INIT = REPO_ROOT / "src" / "agentic_postgres" / "__init__.py"

#: The three classes ADR 0162 defines, and the only words this comment may use
#: for one. `patch` is included although no release has yet taken one through
#: this constant: the guard is against a class that is not a class, not against
#: a class this project happens not to have used.
ADR_0162_CLASSES = ("major", "minor", "patch")


def _comment_block() -> str:
    """Every `#:` line above `CURRENT_SESSION = `, as one string."""
    head, marker, _ = INIT.read_text(encoding="utf-8").partition("CURRENT_SESSION = ")
    assert marker, "CURRENT_SESSION is not assigned in __init__.py"
    lines = [line for line in head.splitlines() if line.startswith("#:")]
    assert lines, "the constant carries no `#:` comment"
    return "\n".join(lines)


def _final_comment_paragraph() -> str:
    """The last `#:` paragraph above `CURRENT_SESSION = `.

    Paragraphs are separated by a bare `#:` line, which is how the whole
    comment block has been written since Session 6. Reading the LAST one is
    deliberate: every bump appends, so the last paragraph is the one that
    prices the release this tree is, and an older paragraph naming an older
    version must not be able to satisfy the assertions below.

    A bump writes several paragraphs and the version-and-class sentence is
    always the last of them; the session it moves to is stated earlier in the
    same append, so that claim is read from the whole block below rather than
    from here.
    """
    paragraph: list[str] = []
    for line in reversed(_comment_block().splitlines()):
        if line.strip() == "#:":
            break
        paragraph.append(line)
    assert paragraph, "the comment block ends on a blank `#:` line"
    return "\n".join(reversed(paragraph))


def test_the_version_file_and_the_constant_agree() -> None:
    """The release's own paragraph names this version and this session.

    Three readings, and each fails on a different mistake: forgetting to move
    the file, forgetting to move the constant, and moving both while leaving
    the paragraph describing the release before.
    """
    version = template_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{version!r} is not a semver triple"

    paragraph = _final_comment_paragraph()

    assert f"`{version}`" in paragraph, (
        f"the final paragraph of CURRENT_SESSION's comment does not name `{version}`, "
        f"which is what the VERSION file says this release is. Append a paragraph for "
        f"this release rather than editing the one that describes the last one.\n\n"
        f"{paragraph}"
    )
    #: Every bump appends a paragraph saying which session it moves the
    #: constant to. Reading the LAST such claim rather than any of them is what
    #: makes this fail on a bump that moved the constant and left the prose at
    #: the release before: the older claims are all still there and true of
    #: their own releases, and a proof that accepted any of them would pass on
    #: a tree whose newest paragraph named the wrong session.
    moves = re.findall(r"moves it to (\d+)", _comment_block())
    assert moves, "no paragraph says which session the constant moves to"
    assert int(moves[-1]) == CURRENT_SESSION, (
        f"the newest paragraph says the constant moves to {moves[-1]}, and "
        f"CURRENT_SESSION is {CURRENT_SESSION}. Append a paragraph for this release "
        f"rather than editing the one that describes the last one."
    )

    #: The version the PREVIOUS release carried must not still be the one the
    #: final paragraph names -- that is the drift this proof exists for, and it
    #: is what a bump that edits the file and forgets the prose looks like.
    major, minor, patch = (int(part) for part in version.split("."))
    previous = f"{major}.{minor - 1}.{patch}" if minor else None
    if previous is not None:
        assert f"`{previous}` moves" not in paragraph, (
            f"the final paragraph still describes {previous} moving. It describes the "
            f"release before this one."
        )


def test_the_constants_comment_states_the_class_it_proposes() -> None:
    """The paragraph prices the release, in ADR 0162's own vocabulary.

    Exactly one class, named as a class rather than mentioned in passing: the
    paragraph says *ADR 0162 prices it a MINOR* and the reading is of that
    sentence, not of any occurrence of the word. `major` appears in every one
    of these paragraphs in the closing sentence about Run 7's stop condition,
    so a proof that merely looked for a class word would read two and could
    not say which was proposed -- D200's shape, a substring standing in for a
    statement.
    """
    paragraph = _final_comment_paragraph()

    priced = re.findall(
        r"ADR 0162 prices it (?:a |an )?([A-Za-z]+)",
        paragraph,
    )
    assert len(priced) == 1, (
        "the final paragraph must price the release exactly once, in the form "
        "`ADR 0162 prices it a MINOR`. Found "
        f"{len(priced)}: {priced}.\n\n{paragraph}"
    )
    (proposed,) = priced
    assert proposed.lower() in ADR_0162_CLASSES, (
        f"{proposed!r} is not one of ADR 0162's classes {ADR_0162_CLASSES}."
    )

    #: A minor and a patch both promise the operator supplies nothing new. The
    #: paragraph has to say which schemas did not move, because that sentence
    #: is what makes the class checkable by a reader rather than asserted by
    #: its author.
    if proposed.lower() in ("minor", "patch"):
        assert "schema moves" in paragraph or "schema move" in paragraph, (
            f"a {proposed.lower()} is a promise that the operator supplies nothing new. "
            "The paragraph must say which of the manifest, outputs, capability, lock "
            f"and secret schemas moved -- none of them, for a {proposed.lower()}.\n\n"
            f"{paragraph}"
        )

    assert "Run 7" in paragraph or "upgrade plan" in paragraph, (
        "the paragraph must name what confirms the class on a deployment; the class "
        "here is PROPOSED, and `upgrade plan` is what prices it against a running "
        f"release.\n\n{paragraph}"
    )
