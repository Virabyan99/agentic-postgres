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
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta
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
    # **D1383.** Session 26 wrote the two pages an operator actually holds and
    # neither was in either scan, so a command named ONLY there read to a walk
    # as undocumented -- the same defect D1323 records for the new-team-member
    # guide, one release later. ADR 0209 makes them release artefacts; this is
    # the half of that decision the live reader keeps.
    "docs/operator-guide.md",
    "docs/upgrade-guide.md",
    # The on-ramp page (ADR 0212) is operator-facing for exactly one audience
    # and is in the scan for D1383's reason, not because it names anything new:
    # measured when it was added, every command on it was already documented
    # elsewhere, so this changed the documented set by nothing. It is here so
    # that the FIRST command named only there is seen.
    "docs/on-ramp.md",
    # **D1881** (Session 35). The guide's steps 11 and 12 send a walker to
    # these three -- proposing a set, composing a workflow, and the one page a
    # connector needs a deployment for -- so a command named only there is
    # documented. In both scans, D1383's rule.
    "docs/workflows.md",
    "docs/connectors.md",
    "docs/change-governance.md",
)

#: The operator guides, which name commands the four pages above do not.
GUIDE_GLOB = "session-*-operator-guide.md"

#: A command as the documentation and the record spell it. Both spellings of the
#: same script are captured here and reduced to one by :func:`normalise`.
#:
#: **THE LIMIT, STATED RATHER THAN DISCOVERED** (D464, D1422). This is a text
#: scan and it captures the script, plus one verb for `bin/apg.sh`. It reads no
#: flags -- not on a continuation line, and not on the same line either, which
#: is wider than the ledger's older wording ("a flag on a backslash-continuation
#: line is unchecked") implies. It does not know whether the command was inside
#: a fenced block, a sentence or a comment; it matches `bin/x.sh` in prose
#: exactly as it matches it in a shell block.
#:
#: The limit is not a defect to be repaired with a parser, and
#: `test_dx_record.py` asserts what it can and cannot see so the statement is a
#: measured property rather than a sentence in a ledger. The direction matters
#: and it is the safe one: an unmatched *documented* command makes a walker's
#: honest use look undocumented, which over-reports gaps rather than hiding
#: them. A parser is a later session's, and it would be a second reader of the
#: documentation with its own idea of what a command is.
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

    # ADR 0290 §1: no `path` is the clone walk, read as ever; `hosted` has
    # its own fields; any other value is left to `shape_problems` to name.
    kind = document.get("path", CLONE)
    required = (
        HOSTED_REQUIRED_FIELDS if kind == HOSTED else REQUIRED_FIELDS if kind == CLONE else ()
    )
    missing = [field for field in required if field not in document]
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
    kind = record.document.get("path", CLONE)
    if kind == HOSTED:
        return hosted_shape_problems(record)
    if kind != CLONE:
        return [
            f"path is {kind!r}; it is absent (the clone walk) or one of {list(PATHS)} (ADR 0290)"
        ]
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
    if record.document.get("path") == HOSTED:
        return problems + _hosted_followed_by_problems(member)
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


def blocked_by_problems(record: Record) -> list[str]:
    """What a walk owes when it did NOT reach the success criterion.

    `blocked_by` is optional and is read only in the case it exists for. The
    task statement (ADR 0207 §1) asks for it, and a field a statement asks for
    and nothing reads is the shape D816, D929 and D1247 each named -- so it has
    a reader from the day it is asked for rather than after the walk that
    needed it.

    Both directions. A failed walk with no `blocked_by` leaves the builder
    knowing the path broke and not where, which costs the second walk §9 allows
    on a search rather than on a repair. A record that reached the criterion
    and still carries one is a record whose two halves disagree, and reading
    only the reassuring half is exactly what §7 warns about.
    """
    value = record.document.get("blocked_by")
    if record.reached_success_criterion is True:
        if value in (None, "", [], {}):
            return []
        return [
            f"blocked_by is set ({value!r}) on a record that says the success criterion was "
            "reached. One of the two is wrong and the record does not say which"
        ]
    if value is None:
        return [
            "reached_success_criterion is not true and blocked_by is absent. The record says "
            "the walk did not finish and not where it stopped, which is the one thing a "
            "failed walk is for"
        ]
    if not isinstance(value, str) or not value.strip():
        return [
            f"blocked_by is {type(value).__name__} and must be a non-empty sentence naming "
            "the step the walk stopped at and what it was refused by"
        ]
    return []


def missing_documents(record: Record) -> list[str]:
    """Documents the walk should have read and the record does not name.

    The minimum is the four pages the task statement hands the walker. A record
    that digests one of them and not the others has recorded a fraction of what
    it was measured against.
    """
    return [relative for relative in DOCUMENT_ROOTS if relative not in record.documents_read]


# ---------------------------------------------------------------------------
# The hosted record (Session 46, ADR 0290)
# ---------------------------------------------------------------------------
#
# A person who did not build Stage 5 walks the PUBLISHED site from an account
# invitation link -- no clone, no `bin/`, no repository file -- so the clone
# reading above cannot describe the walk at all: its documents are repository
# files, its commands scripts, its context a clone. A record with `path:
# "hosted"` is read here instead, by the same rule: every reader is total over
# a malformed record, names its problem and returns.

#: The two record paths. A record without `path` is the clone walk, read by
#: everything above exactly as ADR 0207 reads it (ADR 0290 §1).
CLONE = "clone"
HOSTED = "hosted"
PATHS = (CLONE, HOSTED)

#: What a hosted record must carry (ADR 0290 §2). `blocked_by` is ADR 0207's
#: and stays optional, read by :func:`blocked_by_problems` for both paths.
HOSTED_REQUIRED_FIELDS = (
    "path",
    "followed_by",
    "started_at",
    "completed_at",
    "release",
    "site_commit",
    "site_digest",
    "documents_read",
    "commands_run",
    "files_edited",
    "goals",
    "timeline",
    "undocumented_steps",
    "reached_success_criterion",
    "transcribed_by",
    "confirmed_by_walker_at",
)

#: What a hosted walker held, each of which `followed_by.context` must name.
HOSTED_CONTEXT_WORDS = ("site", "invitation", "statement")

#: The moments the statement asks the person to note (D2866): each an instant,
#: or null for *not noted* -- never a zero (D600).
TIMELINE_FIELDS = (
    "link_opened",
    "account_created",
    "factor_enrolled",
    "organization_created",
    "creation_accepted",
    "connection_string",
)

#: The statement the person is handed, and its markers (ADR 0290 §6).
STATEMENT = "docs/hosted-walk.md"
_STATEMENT_BEGIN = "<!-- walk-statement:begin -->"
_STATEMENT_END = "<!-- walk-statement:end -->"
#: One goal line of the statement's notes form: `  1 connect:  reached at ...`.
_GOAL_LINE = re.compile(r"^\s+(\d+) ([^:]+):")

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: What no record may hold (ADR 0290 §3, D2868): the transcriber refuses them
#: first and this reader refuses them again. Each names its place, never its
#: value. The 43-character run is a handoff token's shape (`token_urlsafe(32)`).
_SECRETS = (
    (
        re.compile(r"postgres(?:ql)?://[^/\s:@]+:[^@\s]+@", re.IGNORECASE),
        "a connection string with a password",
    ),
    (re.compile(r"/accept#"), "an invitation link"),
    (re.compile(r"otpauth://", re.IGNORECASE), "an otpauth URI"),
    (
        re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
        "a 43-character base64url run (a handoff token's shape)",
    ),
)


@dataclass(frozen=True)
class HostedSite:
    """What a hosted record is read against: the site this checkout builds."""

    digest: str
    version: str
    routes: frozenset[str]
    lines: tuple[str, ...]
    goals: tuple[str, ...]


def statement_goals(tree: Path) -> tuple[str, ...]:
    """The goals of the statement's notes form, in its order, read from the
    statement itself -- never a typed copy. Empty when the statement or its
    markers are missing, which :func:`hosted_problems` then reports."""
    path = tree / STATEMENT
    if not path.is_file():
        return ()
    text = path.read_text(encoding="utf-8")
    if _STATEMENT_BEGIN not in text or _STATEMENT_END not in text:
        return ()
    statement = text.split(_STATEMENT_BEGIN, 1)[1].split(_STATEMENT_END, 1)[0]
    if "GOALS:" not in statement:
        return ()
    goals: list[str] = []
    for line in statement.split("GOALS:", 1)[1].splitlines()[1:]:
        match = _GOAL_LINE.match(line)
        if not match:
            break
        goals.append(match.group(2).strip())
    return tuple(goals)


def hosted_site() -> HostedSite:
    """The site at this checkout: `site_build`'s digest and routes, every line a
    page shows as code -- each fenced line and each inline code span, the
    second because a page gives a command in a sentence too (D2916) -- the
    VERSION the banner prints, and the statement's goals."""
    from agentic_postgres import site_build

    lines: list[str] = []
    for page in site_build.pages():
        fenced = False
        for raw in page.body.splitlines():
            if raw.startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                if raw.strip():
                    lines.append(_spaced(raw))
                continue
            lines.extend(_spaced(span) for span in re.findall(r"`([^`]+)`", raw))
    root = site_build.REPO_ROOT
    return HostedSite(
        digest=site_build.digest(),
        version=(root / "VERSION").read_text(encoding="utf-8").strip(),
        routes=frozenset(page.route for page in site_build.pages()),
        lines=tuple(dict.fromkeys(lines)),
        goals=statement_goals(root),
    )


def _spaced(text: str) -> str:
    return " ".join(text.split())


def _instant(value: Any) -> datetime | None:
    """An ISO 8601 instant in UTC, or None."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
        return None
    return moment


def hosted_shape_problems(record: Record) -> list[str]:
    """`shape_problems` for the hosted path: every member the right type."""
    document = record.document
    problems: list[str] = []
    for field in ("commands_run", "files_edited", "undocumented_steps", "documents_read"):
        value = document.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            problems.append(f"{field} is a {type(value).__name__}, not a list of strings")
    if not isinstance(record.reached_success_criterion, bool):
        problems.append(
            f"reached_success_criterion is {record.reached_success_criterion!r}, not true or false"
        )
    for field in ("started_at", "completed_at", "confirmed_by_walker_at"):
        if _instant(document.get(field)) is None:
            problems.append(f"{field} is {document.get(field)!r}, not an ISO 8601 instant in UTC")
    if not isinstance(document.get("release"), str) or not document["release"].strip():
        problems.append(f"release is {document.get('release')!r}, not the banner's text")
    for field, pattern, what in (
        ("site_commit", _SHA1, "40 lowercase hex"),
        ("site_digest", _SHA256, "64 lowercase hex"),
    ):
        value = document.get(field)
        if not isinstance(value, str) or not pattern.match(value):
            problems.append(f"{field} is {value!r}, not {what}")
    goals = document.get("goals")
    if not isinstance(goals, list):
        problems.append(f"goals is a {type(goals).__name__}, not a list of the statement's goals")
    else:
        for index, goal in enumerate(goals):
            problems.extend(_goal_problems(index, goal))
    timeline = document.get("timeline")
    if not isinstance(timeline, dict) or set(timeline) != set(TIMELINE_FIELDS):
        problems.append(f"timeline must be an object of exactly {list(TIMELINE_FIELDS)}")
    else:
        for field in TIMELINE_FIELDS:
            if timeline[field] is not None and _instant(timeline[field]) is None:
                problems.append(
                    f"timeline.{field} is {timeline[field]!r}; an instant, or null for not noted"
                )
    transcribed = document.get("transcribed_by")
    if not isinstance(transcribed, dict) or not all(
        isinstance(transcribed.get(field), str) and transcribed[field].strip()
        for field in ("kind", "identity")
    ):
        problems.append("transcribed_by must be an object of a non-empty kind and identity")
    return problems


def _goal_problems(index: int, goal: Any) -> list[str]:
    if not isinstance(goal, dict):
        return [f"goals[{index}] is a {type(goal).__name__}, not an object"]
    problems: list[str] = []
    if not isinstance(goal.get("goal"), str):
        problems.append(f"goals[{index}].goal is {goal.get('goal')!r}, not a goal's name")
    if not isinstance(goal.get("reached"), bool):
        problems.append(f"goals[{index}].reached is {goal.get('reached')!r}, not true or false")
    if goal.get("at") is not None and _instant(goal.get("at")) is None:
        problems.append(f"goals[{index}].at is {goal.get('at')!r}; an instant, or null")
    note = goal.get("note")
    if goal.get("reached") is False and (not isinstance(note, str) or not note.strip()):
        problems.append(
            f"goals[{index}] was not reached and carries no note: the person's words on why "
            "are the record's point"
        )
    return problems


def _hosted_followed_by_problems(member: dict[str, Any]) -> list[str]:
    """ADR 0290 §2, §6: a person, holding the site, an invitation and the statement."""
    problems: list[str] = []
    if member.get("kind") != "person":
        problems.append(
            f"followed_by.kind is {member.get('kind')!r}; on the hosted path it must be "
            "'person' -- an agent's or a driver's walk is the journey's, never this record's"
        )
    context = member.get("context")
    if isinstance(context, str):
        lowered = context.lower()
        for word in HOSTED_CONTEXT_WORDS:
            if word not in lowered:
                problems.append(
                    f"followed_by.context does not mention the {word}; a hosted walker holds "
                    "the site's URL, an invitation link and the statement, and the record says so"
                )
    return problems


def hosted_unnamed_commands(commands: list[str], site: HostedSite) -> list[str]:
    """Commands typed that no line of the site gives (ADR 0290 §3).

    An `apg` command matches a documented line with its `apg <noun> <verb>` --
    the words before its first flag -- and every flag it used, values free
    (D2893: the site's lines carry placeholders). Any other command matches a
    documented line after whitespace is normalised.
    """
    shapes = [shape for shape in map(_apg_shape, site.lines) if shape is not None]
    spaced = set(site.lines)
    unnamed: list[str] = []
    for command in commands:
        shape = _apg_shape(command)
        if shape is None:
            if _spaced(command) not in spaced:
                unnamed.append(command)
            continue
        words, flags = shape
        if not any(words == known and flags <= given for known, given in shapes):
            unnamed.append(command)
    return unnamed


def _apg_shape(line: str) -> tuple[tuple[str, ...], frozenset[str]] | None:
    try:
        words = shlex.split(line)
    except ValueError:
        return None
    if not words or words[0] != "apg":
        return None
    flags = [word.split("=", 1)[0] for word in words[1:] if word.startswith("-")]
    leading: list[str] = []
    for word in words[1:]:
        if word.startswith("-"):
            break
        leading.append(word)
    return tuple(leading[:2]), frozenset(flags)


def _strings(value: Any, place: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(place, value)]
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in _strings(item, f"{place}.{key}")]
    if isinstance(value, list):
        return [
            found
            for index, item in enumerate(value)
            for found in _strings(item, f"{place}[{index}]")
        ]
    return []


def hosted_secrets(record: Record) -> list[str]:
    """Every place a secret's shape sits in the record, the value never echoed."""
    found: list[str] = []
    for key, value in record.document.items():
        for place, text in _strings(value, key):
            for pattern, what in _SECRETS:
                if pattern.search(text):
                    found.append(f"{place} holds {what}; describe it instead (D2868)")
    return found


def hosted_problems(record: Record, site: HostedSite) -> list[str]:
    """The hosted readings (ADR 0290 §3): the site, the routes, the commands,
    no secret, the hands -- plus the goals against the statement and the
    criterion against the first goal. Total over a malformed record."""
    document = record.document
    problems: list[str] = []
    walked = document.get("site_digest")
    if walked != site.digest:
        shown = walked[:12] if isinstance(walked, str) else repr(walked)
        problems.append(
            f"the site moved after the walk: walked at {shown}, this checkout builds "
            f"{site.digest[:12]}"
        )
    release = document.get("release")
    if release != f"Release {site.version}":
        problems.append(
            f"release is {release!r}; this checkout's banner says 'Release {site.version}'"
        )
    routes = document.get("documents_read")
    for route in routes if isinstance(routes, list) else []:
        if isinstance(route, str) and route not in site.routes:
            problems.append(f"documents_read names {route!r}, which the site does not have")
    commands = document.get("commands_run")
    for command in hosted_unnamed_commands(
        [c for c in commands if isinstance(c, str)] if isinstance(commands, list) else [], site
    ):
        problems.append(f"a command no page of the site gives: {command}")
    edited = document.get("files_edited")
    if isinstance(edited, list) and edited:
        problems.append(f"a hosted walk edits no product file, and this one names {edited}")
    problems.extend(hosted_secrets(record))
    goals = document.get("goals")
    names = (
        tuple(g.get("goal") for g in goals if isinstance(g, dict))
        if isinstance(goals, list)
        else ()
    )
    if not site.goals:
        problems.append(f"{STATEMENT} names no goals between its markers: nothing to read against")
    elif names != site.goals:
        problems.append(
            f"goals are {list(names)}; the statement's are {list(site.goals)}, in that order"
        )
    first = goals[0] if isinstance(goals, list) and goals and isinstance(goals[0], dict) else {}
    if record.reached_success_criterion != first.get("reached"):
        problems.append(
            "reached_success_criterion does not equal the first goal's reached: the criterion "
            "is the working connection string"
        )
    transcribed = document.get("transcribed_by")
    if not isinstance(transcribed, dict) or transcribed.get("kind") != "agent":
        problems.append(
            "transcribed_by.kind must be 'agent': the agent types the person's notes (D2868)"
        )
    started, completed = (
        _instant(document.get("started_at")),
        _instant(document.get("completed_at")),
    )
    confirmed = _instant(document.get("confirmed_by_walker_at"))
    if started and completed and started > completed:
        problems.append("started_at is after completed_at")
    if completed and confirmed and confirmed < completed:
        problems.append(
            "confirmed_by_walker_at is before completed_at: the person confirms the typed "
            "record after the walk, never before it"
        )
    return problems
