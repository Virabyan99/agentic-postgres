#!/usr/bin/env python3
"""Read a second walk's record, or fill in the digests it needs.

Reached as `apg dx-record` (ADR 0093). `bin/dx-record.sh` decides every argument
error before this runs; what is left here is the readings and the report.

**This exists so the walker can see their own verdict** (ADR 0207 §3). The same
four functions decide `DX-001` during the host sweep, and a walker who could not
run them would be marked by a rubric they never saw -- which is a documented
path with an undocumented step in it, in the one claim about undocumented steps.

Exit codes (runbook §2 convention):
  0  the record is clean: no source edit, no unnamed command, no moved
     document, a `followed_by` of the shape ADR 0207 admits, and a
     `blocked_by` that agrees with `reached_success_criterion`
  2  invalid operator input, or a record that cannot be read at all
  3  the record names a document this checkout does not have -- the reading is
     being made from the wrong checkout, which is not the record's fault
  5  the record is readable and one of the five readings has findings

**A hosted record** (`path: "hosted"`, Session 46, ADR 0290) is a person's walk
of the published site from an invitation link. `check` reads it against the
site THIS checkout builds -- its digest, its routes, every line it shows as code
-- and the statement's goals; `digest` refuses it (exit 2): it names routes,
never repository files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import REPO_ROOT, dx_record


def report(title: str, findings: list[str]) -> None:
    """One reading, printed as a list or as `none`.

    `none` rather than silence: a reading that printed nothing when it found
    nothing would be indistinguishable from a reading that did not run, and
    that is the shape this repository keeps producing.
    """
    if not findings:
        print(f"{title}: none")
        return
    print(f"{title}: {len(findings)}")
    for finding in findings:
        print(f"  - {finding}")


def check(record_path: Path, slug_override: str | None, path: str | None = None) -> int:
    try:
        record = dx_record.load(record_path)
    except dx_record.RecordUnreadable as problem:
        print(f"dx-record: {problem}", file=sys.stderr)
        return 2
    except dx_record.RecordIncomplete as problem:
        print(f"dx-record: {problem}", file=sys.stderr)
        return 2

    kind = record.document.get("path", dx_record.CLONE)
    if path is not None and path != kind:
        print(f"dx-record: --path {path}, and the record says it is {kind!r}", file=sys.stderr)
        return 2
    if kind == dx_record.HOSTED:
        return check_hosted(record_path, record)

    if slug_override:
        record = dx_record.Record(
            path=record.path,
            document={**record.document, "project_slug": slug_override},
        )

    shape = dx_record.shape_problems(record)
    if shape:
        report("record shape", shape)
        print(
            "dx-record: the record's shape is wrong, so the five readings below would be "
            "answering a different question.",
            file=sys.stderr,
        )
        return 2

    absent = dx_record.absent_documents(record, REPO_ROOT)
    if absent:
        report("documents this checkout does not have", absent)
        print(
            f"dx-record: {record_path} names documents that are not in {REPO_ROOT}. Read it "
            "from the checkout the walk was made against.",
            file=sys.stderr,
        )
        return 3

    print(f"record: {record_path}")
    print(f"project slug: {record.project_slug}")
    print(f"release: {record.document.get('release')}")
    print(f"reached the success criterion: {record.reached_success_criterion}")
    print()

    edits = dx_record.source_edits(record)
    unnamed = dx_record.unnamed_commands(record, dx_record.documented_commands(REPO_ROOT))
    stale = dx_record.stale_documents(record, REPO_ROOT)
    followed_by = dx_record.followed_by_problems(record)
    blocked_by = dx_record.blocked_by_problems(record)
    unread = dx_record.missing_documents(record)

    report("source edits", edits)
    report("commands the documentation does not name", unnamed)
    report("documents that moved after the walk", stale)
    report("followed_by", followed_by)
    report("blocked_by", blocked_by)
    report("documents the walk did not record reading", unread)
    report("undocumented steps the walker recorded", record.undocumented_steps)

    findings = bool(edits or unnamed or stale or followed_by or blocked_by)
    if record.reached_success_criterion is not True:
        findings = True
        print()
        print("dx-record: the record says the success criterion was not reached.")
    if record.undocumented_steps:
        findings = True
        print()
        print(
            "dx-record: the walker needed steps the documentation does not give, which is "
            "precisely what DX-001 asserts does not happen."
        )

    print()
    if findings:
        print(
            "dx-record: this record does not close DX-001. Every finding above is the "
            "documentation's, not the walker's."
        )
        return 5
    if unread:
        print(
            "dx-record: clean, but the record does not name every document the task "
            f"statement hands a walker ({unread}). Run `dx-record digest` from the walk's "
            "own checkout."
        )
    print("dx-record: clean.")
    return 0


def check_hosted(record_path: Path, record: dx_record.Record) -> int:
    """ADR 0290 §3's readings, against the site this checkout builds."""
    shape = dx_record.shape_problems(record)
    if shape:
        report("record shape", shape)
        print(
            "dx-record: the record's shape is wrong, so the readings below would be answering "
            "a different question.",
            file=sys.stderr,
        )
        return 2
    site = dx_record.hosted_site()
    print(f"record: {record_path}")
    print("path: hosted (a person's walk of the site, ADR 0290)")
    print(f"release: {record.document.get('release')}")
    walked = str(record.document.get("site_digest"))[:12]
    print(f"site walked: {walked}, built here: {site.digest[:12]}")
    print(f"reached the success criterion: {record.reached_success_criterion}")
    print()

    followed_by = dx_record.followed_by_problems(record)
    blocked_by = dx_record.blocked_by_problems(record)
    readings = dx_record.hosted_problems(record, site)
    later = [
        f"{goal['goal']}: {goal.get('note')}"
        for goal in record.document["goals"][1:]
        if goal.get("reached") is False
    ]
    report("followed_by", followed_by)
    report("blocked_by", blocked_by)
    report("the site, routes, commands, secrets and hands", readings)
    report("undocumented steps the walker recorded", record.undocumented_steps)
    report("goals after the first not reached (reported, not findings)", later)

    findings = bool(followed_by or blocked_by or readings or record.undocumented_steps)
    if record.reached_success_criterion is not True:
        findings = True
        print()
        print("dx-record: the record says the person did not reach a working connection string.")
    print()
    if findings:
        print(
            "dx-record: this record does not close documented_path. Every finding above is "
            "the site's, not the person's."
        )
        return 5
    print("dx-record: clean.")
    return 0


def digest(record_path: Path) -> int:
    """Rewrite `documents_read` from this tree, and say what was digested.

    The walker runs this at the end of their walk, in their own clone. Typing
    four sha256 sums by hand is a step the documentation would have to describe
    and nobody would perform correctly, and a record with a wrong digest reads
    exactly like a document that moved.
    """
    try:
        raw = json.loads(record_path.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"dx-record: {record_path} could not be read: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"dx-record: {record_path} is not readable JSON: {error}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print(f"dx-record: {record_path} is not a JSON object", file=sys.stderr)
        return 2
    if raw.get("path") == dx_record.HOSTED:
        print(
            f"dx-record: {record_path} is a hosted record; it names site routes, never "
            "repository files, so there is nothing to digest",
            file=sys.stderr,
        )
        return 2

    computed = dx_record.digests(REPO_ROOT, list(dx_record.DOCUMENT_ROOTS))
    if not computed:
        print(
            f"dx-record: none of {list(dx_record.DOCUMENT_ROOTS)} is present in {REPO_ROOT}. "
            "This is not a checkout of the release.",
            file=sys.stderr,
        )
        return 3

    raw["documents_read"] = computed
    record_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"dx-record: wrote documents_read into {record_path}")
    for relative, value in sorted(computed.items()):
        print(f"  {value[:12]}  {relative}")
    absent = [name for name in dx_record.DOCUMENT_ROOTS if name not in computed]
    if absent:
        print(f"  (not in this checkout, so not digested: {absent})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="verb", required=True)

    checker = subparsers.add_parser("check")
    checker.add_argument("--record", type=Path, required=True)
    checker.add_argument("--project-slug", default=None)
    checker.add_argument("--path", choices=dx_record.PATHS, default=None)

    digester = subparsers.add_parser("digest")
    digester.add_argument("--record", type=Path, required=True)
    digester.add_argument("--path", choices=dx_record.PATHS, default=None)

    arguments = parser.parse_args()

    if arguments.verb == "check":
        return check(arguments.record, arguments.project_slug, arguments.path)
    if arguments.path == dx_record.HOSTED:
        print("dx-record: digest is the clone walk's; a hosted record has nothing to digest",
              file=sys.stderr)  # fmt: skip
        return 2
    return digest(arguments.record)


if __name__ == "__main__":
    sys.exit(main())
