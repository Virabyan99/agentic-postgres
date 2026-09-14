"""Reading the record a second walk writes (ADR 0207 §1 and §3).

`DX-001` says *a developer who did not build the primitive completes the
documented path without source edits or undocumented commands*. Nothing in a
repository can observe that happening, so the walker writes a record and the
product reads it -- and **the reading is the claim**, which is why it lives here
rather than inside the proof that consumes it. A record is checked by
`bin/apg.sh dx-record check` before the walk ends, by the live proof during the
sweep, and by both through the same four functions. A walker who cannot see the
verdict a sweep will reach is a walker being marked by a hidden rubric.

**Every function is total over a malformed record.** A record is written by
somebody who has never seen this repository, possibly by hand, and the useful
answer to a list where a dict belongs is *the record's `followed_by` is a list*
-- not a `TypeError` from four frames down. So each reader names its problem and
returns; only :func:`load` raises, and only for the two failures that stop every
other reading (ADR 0195: three outcomes, and the third is reported).

**What changed in Session 25, and why the old reading was wrong.** The first
version of these checks lived in `test_session12_reuse.py`, was written in
Session 12, and had never run against a real record because none had ever been
declared. It compared edited files by BASENAME against five operator inputs --
correct for a product where an adopter owned five files, and false for the one
ADR 0198 made, where an adopter owns a directory. Measured (rig 25d): a walker
who followed README's two tenant sections exactly produced **seven** false
source edits, and basename comparison could not tell their
`projects/<slug>/migrations/manifest.json` from the release's
`migrations/manifest.json`. It also read commands through `bin/apg.sh` and
stopped there, so `bin/apg.sh no-such-verb` passed while `bin/dev.sh up` -- the
spelling `docs/new-team-member.md` uses -- was refused. ADR 0207 §3 authorises
the replacement; every assertion the old reading made is kept and each is
stricter.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: What the record must carry. Each is a question whose answer decides the
#: claim, and an absent one is refused rather than assumed favourable.
#:
#: `project_slug` and `documents_read` are Session 25's (ADR 0207). The slug is
#: what makes a path comparison possible at all -- without it there is no way to
#: tell the walker's own directory from the release's. `documents_read` is what
#: ties the record to the documentation it was walked against: a walk is a
#: measurement of a document at a commit, and a record that cannot say which
#: document it measured is a value that looks measured and is not (D1306).
REQUIRED_FIELDS = (
    "followed_by",
    "completed_at",
    "release",
    "project_slug",
    "commands_run",
    "files_edited",
    "documents_read",
    "undocumented_steps",
    "reached_success_criterion",
)

#: `followed_by` is a structured member, not a line of prose (ADR 0207 §1).
#:
#: It is the field that decides whether the walk counts -- whether the reader
#: held anything but a clone and the task -- and a free-text answer to that
#: cannot be read by anything. `context` is asserted to NAME the clone and the
#: statement rather than merely to exist, because "a fresh session" is a
#: sentence that is true of a session holding the whole plan directory.
FOLLOWED_BY_FIELDS = ("kind", "identity", "instructed_by", "context")

#: The kinds of walker ADR 0207 admits. An agent qualifies, with the residual
#: the ADR names; a person is the stronger record and the claim does not wait
#: for one.
FOLLOWED_BY_KINDS = ("agent", "person")

#: The operator inputs a reader legitimately creates and edits, **at the
#: checkout root and nowhere else**.
#:
#: The five names are Session 12's and are unchanged. What changed is that they
#: are now paths rather than basenames: `capabilities.yaml` at the root is the
#: operator's own input, and `projects/<slug>/capabilities.yaml` is the walker's
#: project file -- which is also fine, but for a different reason, and a check
#: that cannot distinguish them accepts `contracts/capabilities.yaml` too.
OPERATOR_INPUTS = frozenset(
    {
        "project.yaml",
        "capabilities.yaml",
        "host.yaml",
        "project.alpha.yaml",
        "project.beta.yaml",
    }
)

#: A project slug is what the deploy will accept as a directory name. Validated
#: before it is used to build the exclusion prefix, never after: a slug of `..`
#: would otherwise widen "the walker's own directory" to the whole checkout,
#: which is the one thing this reader exists to refuse. `bin/apg.sh` validates a
#: verb the same way and for the same reason.
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

#: The documents a walker is expected to read, and the ones the documented-
#: command scan is taken from.
#:
#: `docs/new-team-member.md` is here and was not in the Session 12 scan, which
#: is half of D1323: the guide IS the documented path, it spells commands as
#: `bin/<verb>.sh`, and a walker who followed it was told they had used an
#: undocumented command. An absent path is skipped rather than an error --
#: `docs/second-walk.md` does not exist in every release this reader may be
#: asked about.
DOCUMENT_ROOTS = (
    "README.md",
    "docs/README.md",
    "docs/new-team-member.md",
    "docs/second-walk.md",
)

#: The operator guides, which name commands the four pages above do not.
GUIDE_GLOB = "session-*-operator-guide.md"

#: A command as the documentation and the record spell it. Both spellings of the
#: same script are captured here and reduced to one by :func:`normalise`.
_COMMAND = re.compile(
    r"(?:^|[\s`(])(\./deploy\.sh|bin/apg\.sh\s+[a-z][a-z0-9-]*|bin/[a-z0-9-]+\.(?:sh|py))"
)


class RecordUnreadable(ValueError):
    """The file is not there, or is not a JSON object. Nothing can be read."""


class RecordIncomplete(ValueError):
    """The record is a JSON object and does not carry every required field."""


@dataclass(frozen=True)
class Record:
    """A walk's record, loaded and shaped, with the file it came from."""

    path: Path
    document: dict[str, Any]

    @property
    def project_slug(self) -> str:
        slug = self.document.get("project_slug")
        return slug if isinstance(slug, str) else ""

    @property
    def files_edited(self) -> list[str]:
        return _as_string_list(self.document.get("files_edited"))

    @property
    def commands_run(self) -> list[str]:
        return _as_string_list(self.document.get("commands_run"))

    @property
    def documents_read(self) -> dict[str, str]:
        member = self.document.get("documents_read")
        if not isinstance(member, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in member.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    @property
    def reached_success_criterion(self) -> Any:
        return self.document.get("reached_success_criterion")

    @property
    def undocumented_steps(self) -> list[str]:
        return _as_string_list(self.document.get("undocumented_steps"))


def _as_string_list(value: Any) -> list[str]:
    """A list of strings, or an empty one. Never a raise, never a surprise.

    A string is NOT silently treated as a one-element list: a record whose
    `files_edited` is `"projects/x/a.sql"` has answered a different question
    from the one asked, and the shape problem is reported by
    :func:`shape_problems` rather than papered over here.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def load(path: Path) -> Record:
    """The record, or the reason there is not one.

    Three outcomes, and the third is the one that matters: a record that is
    present and incomplete is not the same as a record that is absent, and an
    operator sent to look for a missing file when the file is there and short a
    field will look in the wrong place.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RecordUnreadable(f"{path} could not be read: {error}") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RecordUnreadable(f"{path} is not readable JSON: {error}") from error
    if not isinstance(document, dict):
        raise RecordUnreadable(f"{path} is a {type(document).__name__}, not a JSON object")

    missing = [field for field in REQUIRED_FIELDS if field not in document]
    if missing:
        raise RecordIncomplete(
            f"{path} is missing {missing}. An absent answer is not a favourable one, and a "
            "claim this size is not made on a partial record"
        )
    return Record(path=path, document=document)


def shape_problems(record: Record) -> list[str]:
    """Fields that are present and are the wrong shape.

    Separate from :func:`load`'s completeness check because they are different
    failures with different remedies: a missing field is a question nobody
    answered, and a field of the wrong type is an answer to another question.
    """
    problems: list[str] = []
    for field in ("commands_run", "files_edited", "undocumented_steps"):
        if not isinstance(record.document.get(field), list):
            problems.append(f"{field} is a {type(record.document.get(field)).__name__}, not a list")
    if not isinstance(record.document.get("documents_read"), dict):
        problems.append(
            "documents_read is a "
            f"{type(record.document.get('documents_read')).__name__}, not an object of "
            "{path: sha256}"
        )
    if not isinstance(record.reached_success_criterion, bool):
        problems.append(
            f"reached_success_criterion is {record.reached_success_criterion!r}, not true or false"
        )
    slug = record.document.get("project_slug")
    if not isinstance(slug, str) or not SLUG_PATTERN.match(slug):
        problems.append(
            f"project_slug is {slug!r}; it must match {SLUG_PATTERN.pattern} -- it becomes a "
            "directory prefix, and a slug that is not checked first can widen what counts as "
            "the walker's own"
        )
    return problems


def followed_by_problems(record: Record) -> list[str]:
    """Whether the walker's context was one ADR 0207 admits.

    Not *who* they were -- that is theirs -- but whether the four things that
    make a walk a walk were recorded: what kind of reader, which one, who
    started them, and what they held. D478 is why: a claim closed by its
    author's hands leaves the next reader unable to tell a proved guarantee from
    a plausible one, and the only way to keep the hands apart is to make the
    handover a file that says whose hands they were.
    """
    member = record.document.get("followed_by")
    if not isinstance(member, dict):
        return [
            f"followed_by is a {type(member).__name__}, not an object with "
            f"{list(FOLLOWED_BY_FIELDS)}. ADR 0207 made it structured because it is the field "
            "that decides whether the walk counts, and a sentence cannot be read"
        ]

    problems: list[str] = []
    for field in FOLLOWED_BY_FIELDS:
        value = member.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"followed_by.{field} is {value!r}; it must be a non-empty string")
    if isinstance(member.get("kind"), str) and member["kind"] not in FOLLOWED_BY_KINDS:
        problems.append(
            f"followed_by.kind is {member['kind']!r}; it must be one of {list(FOLLOWED_BY_KINDS)}"
        )
    context = member.get("context")
    if isinstance(context, str):
        lowered = context.lower()
        if "clone" not in lowered:
            problems.append(
                "followed_by.context does not mention the clone. ADR 0207 admits a walker "
                "whose context held nothing but a clone of the release and the task "
                "statement, and 'a fresh session' is a sentence that is also true of a "
                "session holding docs/plans"
            )
        if "statement" not in lowered and "task" not in lowered:
            problems.append("followed_by.context does not mention the task statement it was given")
    return problems


def source_edits(record: Record) -> list[str]:
    """Files the walker edited that are not theirs to edit.

    **By path, and the path is the whole repair** (D1304). A file is the
    walker's own when it is under `projects/<their slug>/`, which is the
    directory ADR 0198 gave an adopter, or when it is one of the five operator
    inputs AT THE CHECKOUT ROOT. Everything else is a source edit, which is
    `DX-001`'s stated failure -- editing a shipped file forks the template.

    The old comparison was by basename and could not tell the walker's
    `projects/<slug>/migrations/manifest.json` from the release's
    `migrations/manifest.json`. This is a widening (the walker's whole
    directory is theirs) and a tightening (a `capabilities.yaml` in some third
    place is now an edit) at the same time.
    """
    slug = record.project_slug
    own_prefix = f"projects/{slug}/" if SLUG_PATTERN.match(slug) else None

    edits: list[str] = []
    for name in record.files_edited:
        normal = _normalise_path(name)
        if own_prefix and normal.startswith(own_prefix):
            continue
        if "/" not in normal and normal in OPERATOR_INPUTS:
            continue
        edits.append(normal)
    return sorted(set(edits))


def _normalise_path(name: str) -> str:
    """A record's path as this repository writes one: relative, no `./`."""
    return name.strip().lstrip("./") if name.strip().startswith("./") else name.strip()


def normalise(command: str) -> str:
    """One spelling for one script.

    `bin/apg.sh dev` and `bin/dev.sh` are the same command. The documentation
    uses both -- README says `bin/apg.sh dev up` and the guides say
    `bin/dev.sh` -- and a comparison that does not know it fails in both
    directions at once: it passes `bin/apg.sh no-such-verb`, because that
    reduces to a script README names, and it refuses `bin/dev.sh up`, because
    that spelling appears in no document the old scan read (D1305, D1323).

    So both sides are reduced to the script, and a verb the documentation never
    names has nowhere to hide.
    """
    text = command.strip().lstrip("./")
    match = re.match(r"^bin/apg\.sh\s+([a-z][a-z0-9-]*)$", text)
    if match:
        verb = match.group(1)
        return "deploy.sh" if verb == "deploy" else f"bin/{verb}.sh"
    return text


def documented_commands(tree: Path) -> set[str]:
    """Every command the documentation names, each reduced to its script."""
    documented: set[str] = set()
    for relative in DOCUMENT_ROOTS:
        path = tree / relative
        if path.is_file():
            documented |= _commands_in(path.read_text(encoding="utf-8"))
    for guide in sorted((tree / "docs").glob(GUIDE_GLOB)):
        documented |= _commands_in(guide.read_text(encoding="utf-8"))
    return documented


def _commands_in(text: str) -> set[str]:
    return {normalise(match.group(1)) for match in _COMMAND.finditer(text)}


def unnamed_commands(record: Record, documented: set[str]) -> list[str]:
    """Commands the walker ran that the documentation does not name.

    `DX-001`'s actual subject: the path is complete only if somebody walked it
    without being told anything that is not written down.
    """
    ran: set[str] = set()
    for line in record.commands_run:
        ran |= _commands_in(f" {line}")
    return sorted(ran - documented)


def digests(tree: Path, paths: list[str]) -> dict[str, str]:
    """`{path: sha256}` for each readable document, in the order given.

    A path that does not exist is absent from the result rather than mapped to
    a null. A missing digest and a digest of nothing are different facts, and
    the caller can tell which it got by comparing the keys (D600).
    """
    computed: dict[str, str] = {}
    for relative in paths:
        path = tree / relative
        if not path.is_file():
            continue
        computed[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return computed


def stale_documents(record: Record, tree: Path) -> list[str]:
    """Documents whose bytes moved between the walk and the reading.

    A docs-only commit between a walk and the sweep is exactly what a walk that
    FOUND something produces, so this is not a rare case -- it is the likely
    one, and reporting it is the difference between a record about this release
    and a record about a release that no longer exists.

    A document the record names and this checkout does not HAVE is
    :func:`absent_documents`, not this. They are different failures with
    different remedies: a moved document means walk again or say why, and an
    absent one means the reading is being made from the wrong checkout.
    """
    moved: list[str] = []
    for relative, recorded in sorted(record.documents_read.items()):
        path = tree / relative
        if not path.is_file():
            continue
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current != recorded:
            moved.append(f"{relative} (walked at {recorded[:12]}, now {current[:12]})")
    return moved


def absent_documents(record: Record, tree: Path) -> list[str]:
    """Documents the record names that this checkout does not have at all."""
    return sorted(relative for relative in record.documents_read if not (tree / relative).is_file())


def missing_documents(record: Record) -> list[str]:
    """Documents the walk should have read and the record does not name.

    The minimum is the four pages the task statement hands the walker. A record
    that digests one of them and not the others has recorded a fraction of what
    it was measured against.
    """
    return [relative for relative in DOCUMENT_ROOTS if relative not in record.documents_read]
