"""The reading taken before a tag is cut (ADR 0214).

Pure. Nothing here runs a process, reads a file or touches the network:
``bin/release-reading.py`` owns every ``git`` invocation and hands the result in
as an :class:`Observation`. That split is what makes the four outcomes testable
without a repository shaped to produce them, and it is what a mutation battery
can reach.

**Why this exists.** A release's documentation has landed one commit past its
own tag three times, twice of them on one day (D1033, D1388, and the pair that
cost ``1.6.2``). ADR 0209 holds a release to its own documentation by a test and
says, correctly, that no test can see a tag cut after CI is green. What was
missing is the question asked out loud at the moment it is answerable.

**What this deliberately does not do.** It does not decide whether a tag is
owed. Rig 28c classified every commit past all five tags as records or release
bytes, and the defect and the ordinary between-releases state are the same
shape: release bytes land within one to five commits of every tag, always,
because the next session starts. What separates *work that belonged inside the
release* from *the next release's work* is intent, and intent is not in the
tree. A verdict here would be invented, which is D1441's mistake — a threshold
on an unmeasured footing — one run earlier in this same session.

So it reports, and it names the judgement it cannot make (ADR 0195). The three
questions in :data:`CHECKLIST` are printed by the command rather than kept on a
page, because a page can go stale, can be skipped by somebody who ran the
command, and asks a person to gather the facts as well as judge them — which is
the arrangement that failed five times out of five.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CHECKLIST",
    "NOTHING_TO_DECIDE",
    "NO_TAGS_IN_THIS_CLONE",
    "OUTCOMES",
    "ROOT_GROUP",
    "TAG_DOES_NOT_CONTAIN_THESE",
    "TAG_IS_OWED",
    "Observation",
    "Reading",
    "group_paths",
    "read",
    "render",
]

#: The tree's ``VERSION`` has no tag anywhere in this clone. A tag is owed on
#: some commit, and the reading says what it would contain.
TAG_IS_OWED = "tag_is_owed"

#: The tree's ``VERSION`` is tagged and commits have landed since that tag.
#: **This is the normal state of a repository between releases** (45 of this
#: repository's first 147 commits), and it is also the shape of the failure that
#: cost ``1.0.1`` and ``1.6.2``. The command cannot tell them apart and says so.
TAG_DOES_NOT_CONTAIN_THESE = "tag_does_not_contain_these"

#: The tree's ``VERSION`` is tagged and the tag is on this commit, or nothing
#: has landed since it.
NOTHING_TO_DECIDE = "nothing_to_decide"

#: ADR 0195's third outcome, and it is not hypothetical: ``actions/checkout``
#: fetches no tags unless asked, and two of this repository's three CI jobs use
#: the default. Measured against a control — a depth-1 clone reports zero tags
#: and ``git describe`` is fatal, where a full clone of the same commit reports
#: five. A reading taken there would be clean by measuring nothing.
NO_TAGS_IN_THIS_CLONE = "no_tags_in_this_clone"

#: Every outcome, in the order a reader meets them.
OUTCOMES = (
    TAG_IS_OWED,
    TAG_DOES_NOT_CONTAIN_THESE,
    NOTHING_TO_DECIDE,
    NO_TAGS_IN_THIS_CLONE,
)

#: The judgement the command does not make, asked of the person who ran it.
#:
#: Three questions, in the second person, unanswered. They are a constant rather
#: than a page for the reason the module docstring gives, and the first one is
#: the one nobody asked before any of the five tags.
CHECKLIST = (
    "Does everything in this window belong inside {version}?",
    "Is there anything you intended to be in {version} that is not in this list?",
    "Is this commit the one the tag goes on?",
)


@dataclass(frozen=True)
class Observation:
    """What ``git`` and the checkout said, before anything is concluded from it.

    Every field is something the caller measured. ``tags`` empty means this
    clone has none — which is a different fact from *this repository has no
    tags*, and the reading refuses to tell them apart rather than guessing.
    """

    #: ``HEAD``'s full commit id, or ``""`` when it could not be read.
    head: str = ""
    #: The tree's ``VERSION``, verbatim.
    version: str = ""
    #: Every tag name in this clone. Empty is the third outcome, not a fact
    #: about the repository.
    tags: tuple[str, ...] = ()
    #: Tags pointing at ``HEAD``.
    tags_on_head: tuple[str, ...] = ()
    #: The most recent tag reachable from ``HEAD``, or ``""``.
    last_tag: str = ""
    #: That tag's commit id, its ISO date and the ``VERSION`` it carries.
    last_tag_commit: str = ""
    last_tag_date: str = ""
    last_tag_version: str = ""
    #: Whether a tag carrying the tree's ``VERSION`` exists in this clone, and
    #: which one. A release is tagged when its *version* is, not when ``HEAD``
    #: is: ``1.6.1``'s tag sits one commit past its own bump.
    version_tag: str = ""
    #: The tag the window below is measured from: the one carrying the tree's
    #: ``VERSION`` when that exists, and the last reachable tag otherwise. They
    #: are the same tag in every ordinary case and the field exists so the
    #: sentence and the count can never name two different tags.
    window_tag: str = ""
    #: Commits and changed paths between ``window_tag`` and ``HEAD``.
    commits_since_tag: int = 0
    paths_since_tag: tuple[str, ...] = ()
    #: The commit that last moved ``VERSION``, what else moved in it, and what
    #: has landed after it. The bump commit is where the release is declared, so
    #: this is the window in which *does this belong inside the release* has a
    #: right answer.
    bump_commit: str = ""
    bump_subject: str = ""
    bump_paths: tuple[str, ...] = ()
    commits_since_bump: int = 0
    paths_since_bump: tuple[str, ...] = ()
    #: Counts that move in every release and that nobody reconstructs by hand.
    #: ``None`` where the count could not be read — never zero, which would read
    #: as measured (D600).
    released_migrations_at_tag: int | None = None
    released_migrations_in_tree: int | None = None
    adrs_at_tag: int | None = None
    adrs_in_tree: int | None = None


@dataclass(frozen=True)
class Reading:
    """An :class:`Observation` with one of :data:`OUTCOMES` attached."""

    outcome: str
    observation: Observation
    #: One sentence naming what was found. Never an instruction.
    summary: str = ""
    #: The questions the command asks and does not answer. Empty only when the
    #: reading could not be taken.
    questions: tuple[str, ...] = field(default_factory=tuple)


def read(observation: Observation) -> Reading:
    """Classify an observation into exactly one of :data:`OUTCOMES`.

    The order matters. *No tags in this clone* is tested first, because every
    other outcome is a statement about tags and would otherwise be answered from
    their absence.
    """
    if not observation.tags:
        return Reading(
            outcome=NO_TAGS_IN_THIS_CLONE,
            observation=observation,
            summary=(
                "this clone holds no tags, so the reading cannot be taken here. "
                "A shallow checkout and `--no-tags` both look exactly like a "
                "repository that has never been tagged"
            ),
            questions=(),
        )

    version = observation.version or "(no VERSION)"
    questions = tuple(q.format(version=version) for q in CHECKLIST)

    if not observation.version_tag:
        return Reading(
            outcome=TAG_IS_OWED,
            observation=observation,
            summary=(
                f"the tree says {version} and no tag carries it: a tag is owed, "
                "and what follows is what it would contain"
            ),
            questions=questions,
        )

    if observation.commits_since_tag <= 0:
        return Reading(
            outcome=NOTHING_TO_DECIDE,
            observation=observation,
            summary=(
                f"the tree says {version}, tag {observation.version_tag} carries it, "
                "and nothing has landed since: there is nothing to decide"
            ),
            questions=questions,
        )

    window = observation.window_tag or observation.version_tag
    return Reading(
        outcome=TAG_DOES_NOT_CONTAIN_THESE,
        observation=observation,
        summary=(
            f"the tree says {version} and tag {window} carries it, but that tag does "
            f"not contain the {observation.commits_since_tag} commit(s) that have "
            "landed since. Whether they belong inside it is a judgement this "
            "command does not make"
        ),
        questions=questions,
    )


#: What a file at the repository root is grouped under. Named rather than
#: printed as an empty string, which reads as a rendering fault.
ROOT_GROUP = "(repository root)"


def group_paths(
    paths: tuple[str, ...] | list[str], *, depth: int = 2
) -> tuple[tuple[str, int], ...]:
    """Group changed paths by the directory they sit in, commonest first.

    Sixty-one file names are a wall; ``tests/contract 20`` is a sentence. The
    key is the file's DIRECTORY, truncated to ``depth`` components -- grouping
    by the first ``depth`` path components instead puts every ``bin/`` command
    on its own line, which is the wall again with extra steps. Ties sort by
    name, so two runs over one tree print the same bytes.
    """
    counts: dict[str, int] = {}
    for path in paths:
        parts = path.split("/")[:-1]
        key = "/".join(parts[:depth]) if parts else ROOT_GROUP
        counts[key] = counts.get(key, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


#: What the bump line says when ``VERSION`` has never moved in this history --
#: a clone deep enough to hold tags but not the bump, or a fork whose very first
#: commit already carried the file.
_NO_BUMP = "(VERSION has not moved in this history)"


def _count_line(label: str, at_tag: int | None, in_tree: int | None) -> str:
    """One count, or the honest absence of one.

    ``None`` prints as ``?`` rather than ``0``: a count that could not be read
    and a count of zero are different facts, and the second is the one that
    reads as measured (D600).
    """
    left = "?" if at_tag is None else str(at_tag)
    right = "?" if in_tree is None else str(in_tree)
    moved = "" if left == right else "   <- moved"
    return f"    {label:<22} {left:>6} -> {right:<6}{moved}"


def render(reading: Reading, *, ref: str | None = None) -> tuple[str, ...]:
    """The reading as lines, for a terminal.

    ``ref`` is what the operator typed, not the resolved SHA, and it changes
    exactly one thing: the first block says which commit was read. A transcript
    of a reading taken before a tag has to name its subject, or nobody can
    check afterwards that the right commit was read (D1513, ADR 0219). With no
    ref every byte is what it was.

    Facts first, then the questions. Nothing here is coloured, indented by
    guesswork or abbreviated: the two counts at the end are the ones a person
    was never going to reconstruct, and they are the reason this is a command.
    """
    observation = reading.observation
    lines = [
        "The reading before a tag (ADR 0214)",
        "",
        f"  outcome: {reading.outcome}",
        f"  {reading.summary}.",
        "",
    ]

    if reading.outcome == NO_TAGS_IN_THIS_CLONE:
        lines.extend(
            [
                "  Run it in a full clone. `git fetch --tags` in this one, or",
                "  `actions/checkout` with `fetch-depth: 0`, is what it is missing.",
                "",
                f"  {'ref ' + ref if ref else 'HEAD'}     {observation.head[:12] or '(unknown)'}",
                f"  VERSION  {observation.version or '(unreadable)'}",
            ]
        )
        return tuple(lines)

    on_head = ", ".join(observation.tags_on_head) if observation.tags_on_head else "(none)"
    lines.extend(
        [
            f"  Where {('the ref ' + ref) if ref else 'HEAD'} stands",
            f"    commit            {observation.head[:12] or '(unknown)'}",
            f"    VERSION           {observation.version or '(unreadable)'}",
            f"    {('tags on it' if ref else 'tags on HEAD'):<18}{on_head}",
            "",
            "  The last tag",
            f"    name              {observation.last_tag or '(none reachable)'}",
            f"    commit            {observation.last_tag_commit[:12] or '(unknown)'}",
            f"    date              {observation.last_tag_date or '(unknown)'}",
            f"    VERSION at it     {observation.last_tag_version or '(unreadable)'}",
            "",
            f"  What has landed since {observation.window_tag or observation.last_tag or 'it'}",
            f"    commits           {observation.commits_since_tag}",
            f"    files             {len(observation.paths_since_tag)}",
        ]
    )
    for key, count in group_paths(observation.paths_since_tag):
        lines.append(f"      {count:>4}  {key}")

    lines.extend(
        [
            "",
            "  Counts a release moves and nobody remembers",
            _count_line(
                "released migrations",
                observation.released_migrations_at_tag,
                observation.released_migrations_in_tree,
            ),
            _count_line("ADRs", observation.adrs_at_tag, observation.adrs_in_tree),
            "",
            "  The bump, and what landed after it",
            f"    commit            {observation.bump_commit[:12] or _NO_BUMP}",
        ]
    )
    if observation.bump_commit:
        lines.extend(
            [
                f"    subject           {observation.bump_subject}",
                f"    moved with it     {len(observation.bump_paths)} file(s)",
            ]
        )
        for path in observation.bump_paths:
            lines.append(f"      {path}")
        lines.append(f"    commits after it  {observation.commits_since_bump}")
        if observation.paths_since_bump == observation.paths_since_tag:
            # The tag sits on or beside its own bump, which is the healthy
            # arrangement. Printing the identical list twice would train the
            # reader to skip both.
            lines.append("      (the same files as above: the tag sits on its own bump)")
        else:
            for key, count in group_paths(observation.paths_since_bump):
                lines.append(f"      {count:>4}  {key}")

    lines.extend(["", "  What this command does not decide"])
    lines.extend(f"    - {question}" for question in reading.questions)
    lines.extend(
        [
            "",
            "  The tag is your `git tag -a`. This printed what it would carry.",
        ]
    )
    return tuple(lines)
