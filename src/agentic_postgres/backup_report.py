"""Reading `pgbackrest info`, and turning it into what the document publishes.

Pure logic, so that the mapping from a repository's own report to
`backup_state` can be driven without a container -- which matters because the
interesting cases are the ones a healthy deployment never reaches.

**The one thing every reader here must know: `pgbackrest info` exits 0 in every
state.** Measured in rig 6, four phases:

===========================  ===========  ===============  =====================
repository state             `info` exit  `status.code`    `status.message`
===========================  ===========  ===============  =====================
no stanza                    **0**        1                `missing stanza path`
stanza, no backups           **0**        2                `no valid backups`
one full backup              **0**        0                `ok`
a stanza never named at all  **0**        1                `missing stanza path`
===========================  ===========  ===============  =====================

That is D145's shape -- `postgrest --ready` returning 0 while every request
404s -- and it is why nothing in this module looks at an exit code. An observer
built the obvious way, running `info` and checking it succeeded, would report a
healthy repository for a stanza that does not exist, on every project, forever.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

#: `status.code` in `pgbackrest info --output=json`, measured (rig 6).
#:
#: Named rather than compared as bare integers, because `0` here means "ok" and
#: `0` from a process means "it ran" -- and those two zeros are exactly what
#: this module exists to keep apart.
REPOSITORY_OK = 0
REPOSITORY_MISSING_STANZA = 1
REPOSITORY_NO_BACKUPS = 2

#: What `backup_state.status` may be, in the order a repository reaches them.
#:
#: `awaiting_first_backup` is Session 10 Run 6's addition to outputs v13 (ADR
#: 0149) and it exists because the state is real, expected and describable by
#: none of the other three: every project is in it immediately after its first
#: Session 10 deploy, because the first full backup is an operator command at a
#: TTY. `ready` would be false -- nothing can be restored. `failing` would be red
#: on every first deploy, which is a status operators learn to ignore.
#: `unconfigured` is the value for a MISSING CREDENTIAL, so it would send an
#: operator hunting for a secret that is present and correct.
STATUS_NOT_OBSERVED = "not_observed"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_AWAITING_FIRST_BACKUP = "awaiting_first_backup"
STATUS_READY = "ready"
STATUS_FAILING = "failing"


def _timestamp(epoch: int | None) -> str | None:
    """An epoch integer as the document's RFC 3339 UTC, or None.

    `pgbackrest info` reports every time as an integer number of seconds. The
    document's `timestamp` pattern is `...THH:MM:SSZ` with no fractional part
    and no offset, so the conversion is fixed here rather than at each call
    site -- three call sites formatting a time three ways is how one of them
    ends up with an offset the schema refuses.
    """
    if epoch is None:
        return None
    return (
        datetime.fromtimestamp(int(epoch), UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def summarise(document: Any, stanza: str) -> dict[str, Any]:
    """The facts `pgbackrest info --output=json` carries, for one stanza.

    ``document`` is the parsed JSON -- a LIST of stanza objects, even when
    `--stanza` narrowed it to one, which is why this selects by name rather than
    taking ``[0]``. A `--stanza` that matches nothing still returns one entry,
    with `status.code` 1, so an empty list is not how absence arrives.

    Raises nothing for a repository in a bad state: an absent stanza is a fact
    to report, and every caller here has to distinguish it from an unreachable
    repository anyway.
    """
    if not isinstance(document, list):
        raise ValueError(f"pgbackrest info returned {type(document).__name__}, expected a list")

    entries = [entry for entry in document if entry.get("name") == stanza]
    if not entries:
        # Distinct from "code 1". `info` answers for the stanza it was asked
        # about even when that stanza has never existed, so a report with no
        # entry for it means the report is about something else entirely.
        raise ValueError(
            f"pgbackrest info reported on {[e.get('name') for e in document]}, "
            f"which does not include {stanza!r}"
        )
    entry = entries[0]

    status = entry.get("status") or {}
    code = status.get("code")
    backups = entry.get("backup") or []

    fulls = [backup for backup in backups if backup.get("type") == "full"]
    # `info` returns backups oldest first (measured: the full precedes the incr
    # that references it). Sorted on the key that actually orders them rather
    # than trusting that, because a report that changed order would silently
    # publish the OLDEST backup as the newest.
    newest_full = max(fulls, key=lambda b: (b.get("timestamp") or {}).get("stop", 0), default=None)
    newest_any = max(backups, key=lambda b: (b.get("timestamp") or {}).get("stop", 0), default=None)

    return {
        "status_code": code,
        "status_message": status.get("message"),
        "stanza_created": code != REPOSITORY_MISSING_STANZA,
        "backup_count": len(backups),
        "last_full_backup_label": (newest_full or {}).get("label"),
        "last_full_backup_at": _timestamp(((newest_full or {}).get("timestamp") or {}).get("stop")),
        # **A proven floor, not the true latest** (ADR 0149, D550).
        #
        # `pgbackrest info` has NO latest-recoverable-time field: it carries
        # per-backup epochs and WAL SEGMENT NAMES, and a segment name has no
        # time in or beside it. So what is published is the newest backup's stop
        # time -- the latest instant this deployment can PROVE is recoverable.
        # WAL archived afterwards extends real recovery past it, which is why a
        # drill landing later is the floor being a floor rather than a
        # contradiction, and why Run 8's evidence records the ACHIEVED point as
        # a field of its own (D529).
        "latest_recoverable_time": _timestamp(
            ((newest_any or {}).get("timestamp") or {}).get("stop")
        ),
        # Present so a caller can say WHICH backup failed rather than only that
        # the repository is unhappy. pgBackRest sets it per backup.
        "backup_errors": [b.get("label") for b in backups if b.get("error")],
        # Session 31 (ADR 0221): what this stanza actually occupies at the
        # provider, for `doctor usage`.
        #
        # **`delta`, not `size`.** `info.repository.size` is what this backup
        # WOULD occupy alone; `delta` is what it added to the repository given
        # what was already there. An incremental's `size` counts the bytes of
        # the full it references, so summing `size` over a chain counts the
        # same bytes once per backup and produces a total larger than the
        # repository has ever held -- a number that looks measured and is not.
        #
        # `None` when ANY backup lacks the member, never a partial sum: a
        # repository figure that silently omitted one backup would read as a
        # smaller repository rather than as an unread one (D600).
        "repository_bytes": _repository_delta_total(backups),
    }


def _repository_delta_total(backups: list[dict[str, Any]]) -> int | None:
    """The sum of every backup's repository delta, or `None`.

    Separate from `summarise` so the rule -- all of them or none -- is one
    expression a reader can check, rather than a comprehension with a
    conditional buried in a dict literal.
    """
    if not backups:
        # An empty repository occupies nothing, and that IS a measurement: a
        # stanza created and never backed up is a fact, not a failure to read.
        return 0
    total = 0
    for backup in backups:
        delta = ((backup.get("info") or {}).get("repository") or {}).get("delta")
        if not isinstance(delta, int):
            return None
        total += delta
    return total


def status_for(summary: dict[str, Any]) -> str:
    """The ladder, and it reads `status_code` rather than any process's exit.

    ADR 0149's table, in one place so the command and the deploy cannot disagree
    about what a repository's report means.
    """
    code = summary.get("status_code")
    if code == REPOSITORY_MISSING_STANZA:
        # After step 6c has run `stanza-create`, a missing stanza is a real
        # failure rather than a first-deploy state -- the create either did not
        # run or did not take.
        return STATUS_FAILING
    if code == REPOSITORY_NO_BACKUPS:
        return STATUS_AWAITING_FIRST_BACKUP
    if code == REPOSITORY_OK:
        if summary.get("backup_errors"):
            return STATUS_FAILING
        if not summary.get("last_full_backup_label"):
            # `ok` with no FULL backup is not a state rig 6 produced, and it is
            # not assumed impossible either: an incremental cannot exist without
            # its full, but a retention policy that expired the full while
            # keeping a differential would land here. Nothing can be restored
            # from a chain whose base is gone.
            return STATUS_FAILING
        return STATUS_READY
    # An unrecognised code is not success. pgBackRest may add one, and mapping
    # an unknown to `ready` is how a new failure mode arrives as a green light.
    return STATUS_FAILING


#: The one query that reads the archiver, and the ONE place its columns are named.
#:
#: `pg_stat_archiver` is the product's own report, and it is the source for the
#: same reason ADR 0149 refuses a process's exit code: a log line is a third
#: party's formatting decision, and D374 is the record of a test checking a
#: string its target could not contain (D528).
#:
#: `-qtA` with this separator is how `bin/deploy-project.py` already reads the
#: cluster, so the parsing below matches the reader that exists rather than
#: introducing a second shape.
ARCHIVER_QUERY = (
    "SELECT archived_count, coalesce(last_archived_time::text, ''), "
    "failed_count, coalesce(last_failed_time::text, ''), "
    "coalesce(last_failed_wal, '') FROM pg_stat_archiver"
)

ARCHIVER_SEPARATOR = "|"


def parse_archiver(raw: str) -> dict[str, Any] | None:
    """`ARCHIVER_QUERY`'s single row, or None if there is nothing to read.

    None rather than a dict of zeros: a cluster that could not be asked and a
    cluster reporting zero failures are different facts, and publishing the
    second for the first is the substitution `NOT_OBSERVED` exists to refuse.
    """
    line = next((part for part in raw.strip().splitlines() if part.strip()), "")
    if not line:
        return None
    fields = line.split(ARCHIVER_SEPARATOR)
    if len(fields) != 5:
        return None
    archived, archived_at, failed, failed_at, failed_wal = fields
    try:
        archived_count = int(archived)
        failed_count = int(failed)
    except ValueError:
        return None
    return {
        "archived_count": archived_count,
        "last_archived_time": archived_at or None,
        "failed_count": failed_count,
        "last_failed_time": failed_at or None,
        "last_failed_wal": failed_wal or None,
    }


def archiving_is_failing(archiver: dict[str, Any]) -> bool:
    """Is the MOST RECENT archive attempt a failure? (ADR 0150)

    **Timestamps, never the counter**, and rig 7 is why. Measured, arm G, with
    the arm and its control in one invocation:

      healthy baseline   archived 8 -> 12   failed 11 -> 11
      archiving broken   archived 12 -> 12  failed 11 -> 26
      repaired (control) archived 12 -> 21  failed 26 -> 26

    **`failed_count > 0` is unusable as a status** (D553): the healthy,
    fully-caught-up cluster in the last row carries 26. The counter is cumulative
    and never resets, and **every project accrues failures before its stanza
    exists** -- the window between the container starting with `archive_mode=on`
    and step 6c running `stanza-create` is a window in which every attempt
    fails. That predicate would report every project failing, permanently, from
    its first deploy.

    This REFINES D535 rather than contradicting it. D535 says `failed_count` is
    the value that moves while `last_failed_wal` pins to the oldest stuck
    segment, and that is right *for detecting a change across an interval*, which
    is what `REC-WAL-001` asserts. A point-in-time status is a different question.

    `archived_count` is no better on its own: it freezes during the failure and
    then **catches up** (12 -> 21 across the repair), so a reader sampling it
    twice around a repair sees a healthy-looking increase.
    """
    if archiver.get("last_failed_time") is None:
        return False
    if archiver.get("last_archived_time") is None:
        # Something has failed and nothing has ever succeeded.
        return True
    return str(archiver["last_failed_time"]) > str(archiver["last_archived_time"])


def with_archiver(state: dict[str, Any], archiver: dict[str, Any] | None) -> dict[str, Any]:
    """Fold an archiver reading into a state block that is already computed.

    **D701, and it is the reason this exists rather than a second call to
    `backup_state`.** `bin/backup.py info --json` prints `backup_state(...)` —
    the finished block — and `deploy-project.py` parsed that and called
    `backup_state` on it again. The second call reads `summary["status_code"]`,
    which the *state* block does not carry, so no branch of `status_for` matched
    and its final `return STATUS_FAILING` ran.

    That was deterministic: **every deployed document with a backup block
    published `failing`**, whatever the repository's real state, and a redeploy
    could not correct it. Measured on the live host — `bin/backup.sh info --json`
    reported `ready` for both projects while both documents said `failing`, and a
    fresh deploy rewrote one of them to `failing` again.

    It failed *safe*, which is why it survived two sessions: the catch-all exists
    so that an unrecognised pgBackRest code cannot arrive as a green light, and a
    permanent false alarm is the direction that does not let a real failure
    through. It is still a false alarm, and a signal that is always red is a
    signal nobody reads.

    The archiver can only make a status worse, never better — a repository with
    no backup stays `awaiting_first_backup` however well WAL is flowing, because
    there is still nothing to restore.
    """
    if archiver is None:
        return dict(state)
    folded = dict(state)
    if archiving_is_failing(archiver):
        folded["status"] = STATUS_FAILING
    folded["wal_archived_count"] = archiver.get("archived_count")
    folded["wal_failed_count"] = archiver.get("failed_count")
    return folded


def backup_state(summary: dict[str, Any], archiver: dict[str, Any] | None = None) -> dict[str, Any]:
    """The deployed document's `backup_state` block.

    Two sources, deliberately: the repository's own report says whether a backup
    exists and when, and **`pg_stat_archiver` says whether WAL is still
    arriving** (ADR 0150). They fail independently -- a repository full of good
    backups can sit behind an archiver that stopped an hour ago -- so a status
    derived from one alone is a status about half the system.

    ``archiver`` is None when nothing read the cluster: a deployment through a
    session before 10, or a read that failed. Then the two counters stay null,
    which is what Run 6 published for every deployment, and the repository's
    verdict stands alone.

    **The archiver can only make the status worse, never better.** A repository
    with no backup is `awaiting_first_backup` whether or not WAL is flowing, and
    a healthy archiver cannot promote it: there is still nothing to restore.
    """
    status = status_for(summary)
    if archiver is not None and archiving_is_failing(archiver):
        status = STATUS_FAILING

    return {
        "status": status,
        "stanza_created": bool(summary.get("stanza_created")),
        "last_full_backup_label": summary.get("last_full_backup_label"),
        "last_full_backup_at": summary.get("last_full_backup_at"),
        "latest_recoverable_time": summary.get("latest_recoverable_time"),
        # Published AS MEASURED -- cumulative, unreset, and including the
        # failures every project accrues before its stanza exists. They are the
        # diagnostic that justifies the status, not the status itself, and
        # resetting them would make the deploy a writer of the evidence it reads.
        "wal_archived_count": None if archiver is None else archiver["archived_count"],
        "wal_failed_count": None if archiver is None else archiver["failed_count"],
        # Version 16 (ADR 0188). The mirror is a third source, folded in by
        # `with_mirror` from the copy record the deploy reads; the repository's
        # own report says nothing about it, so this block starts not observed.
        "mirror": dict(MIRROR_NOT_OBSERVED),
    }


#: What `backup_state.mirror` says when nothing read the copy record (ADR 0188).
MIRROR_NOT_OBSERVED: dict[str, Any] = {
    "status": "not_observed",
    "last_copied_at": None,
    "objects": None,
}
MIRROR_STATUS_DISABLED = "disabled"
MIRROR_STATUS_NEVER = "never"
MIRROR_STATUS_COPIED = "copied"

#: The copy record, beside the deployed document in the project's state
#: directory: written by `bin/backup.py mirror` on a completed copy and by
#: nothing else, read by the doctor and the deploy. A copy that exits non-zero
#: leaves the previous record in place, so the record always describes the
#: newest COMPLETE copy (D1001: a pass may exit 1 with objects behind).
MIRROR_RECORD_FILENAME = "mirror-state.json"


def mirror_record(*, objects: int, copied_at: datetime, retried: bool = False) -> dict[str, Any]:
    """What the verb writes: the status, when, how many objects the mirror
    bucket listed afterwards, and whether the pass needed a second try.

    Built here so the writer and the parser agree.

    **`retried` does not weaken what the record means** (ADR 0220 §4). A record
    still describes a copy that COMPLETED and a count read after it; `retried`
    says how many passes it took to complete, never that something is
    outstanding. It exists because the flake it records is upstream and no
    change here removes it (D1546): once a single flaked object is corrected by
    an immediate second pass, the unit's exit code stops carrying the rate, and
    this field is where a rising rate becomes visible instead.
    """
    if objects < 0:
        raise ValueError("an object count cannot be negative")
    return {
        "status": MIRROR_STATUS_COPIED,
        "last_copied_at": copied_at.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "objects": objects,
        "retried": bool(retried),
    }


def parse_mirror_record(text: str) -> dict[str, Any] | None:
    """The record read back, or None for anything that is not one.

    None rather than a partial record: a file that says `copied` with no
    timestamp is not a copy this module can vouch for, and a reader that
    published the half it could parse would be D600's null that looks measured.
    """
    try:
        loaded = json.loads(text)
    except ValueError:
        return None
    if not isinstance(loaded, dict) or loaded.get("status") != MIRROR_STATUS_COPIED:
        return None
    copied_at = loaded.get("last_copied_at")
    objects = loaded.get("objects")
    if not isinstance(copied_at, str) or not copied_at:
        return None
    if not isinstance(objects, int) or isinstance(objects, bool) or objects < 0:
        return None
    # **Absent means False, and anything else means this is not a record.** A
    # record written before ADR 0220 carries no `retried`, and `False` is what
    # it meant: that release could not retry. A `retried` that is not a boolean
    # was written by something this parser does not know, and the honest answer
    # is the third outcome -- the doctor reports `unknown` rather than
    # publishing a copy it could not fully read (ADR 0195).
    retried = loaded.get("retried", False)
    if not isinstance(retried, bool):
        return None
    return {
        "status": MIRROR_STATUS_COPIED,
        "last_copied_at": copied_at,
        "objects": objects,
        "retried": retried,
    }


def mirror_reading(*, enabled: bool, record: dict[str, Any] | None) -> dict[str, Any]:
    """The mirror block for one project from the two facts a reader has: does
    the manifest enable a mirror, and is there a copy record. `disabled` for a
    project without one; `never` for one whose mirror has not yet completed a
    copy; the record's `copied` otherwise."""
    if not enabled:
        return {"status": MIRROR_STATUS_DISABLED, "last_copied_at": None, "objects": None}
    if record is None:
        return {"status": MIRROR_STATUS_NEVER, "last_copied_at": None, "objects": None}
    return {
        "status": MIRROR_STATUS_COPIED,
        "last_copied_at": record["last_copied_at"],
        "objects": record["objects"],
    }


def count_listing(text: str) -> int | None:
    """How many objects `mc ls --recursive --json` listed.

    One JSON object per line -- measured on the pinned image (D1004): with
    `--recursive` every line is `"type":"file"` and a prefix appears only as
    part of a key; without it a prefix is its own `"type":"folder"` line. Only
    files are counted, so the count is the same whichever form a caller
    listed. The container image has no `wc`, so the host counts. None when a
    line is not JSON: a listing this cannot read is not zero objects, and zero
    is the count a restore would be planned against.
    """
    objects = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            return None
        if not isinstance(entry, dict):
            return None
        if entry.get("type") == "file":
            objects += 1
    return objects


def with_mirror(state: dict[str, Any], mirror: dict[str, Any] | None) -> dict[str, Any]:
    """Fold the mirror's reading into a computed state block (ADR 0188).

    ``mirror`` is the copy record `bin/backup.py mirror` writes on a successful
    copy -- ``last_copied_at`` and ``objects`` -- or a status alone:
    ``disabled`` for a project without a mirror, ``never`` for one whose mirror
    has not yet completed a copy. None means nothing read it, and the block
    stays `not_observed`: a failed copy is a failed unit and a doctor check,
    never a status here, because the record is written only on success (D1001).
    Like `with_archiver`, this never recomputes the repository's own status.
    """
    folded = dict(state)
    if mirror is None:
        folded["mirror"] = dict(MIRROR_NOT_OBSERVED)
        return folded
    status = str(mirror.get("status") or MIRROR_NOT_OBSERVED["status"])
    copied = status == MIRROR_STATUS_COPIED
    folded["mirror"] = {
        "status": status,
        "last_copied_at": mirror.get("last_copied_at") if copied else None,
        "objects": mirror.get("objects") if copied else None,
    }
    return folded
