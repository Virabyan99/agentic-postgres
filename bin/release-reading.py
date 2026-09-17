#!/usr/bin/env python3
"""Take the reading before a tag is cut (ADR 0214).

Reached as `apg release-reading` (ADR 0093). `bin/release-reading.sh` decides
every argument error before this runs; what is left here is the `git` calls and
the report.

**Every conclusion lives in `agentic_postgres.release_reading`, which reads
nothing.** This file measures and hands over an `Observation`; the four outcomes
and the rendering are pure, so a battery can reach them without a repository
shaped to produce each one.

**Nothing here writes, and nothing here tags.** A tag is an irreversible
publication and it is the operator's own `git tag -a`, as it has been for all
five of this repository's tags.

Exit codes (runbook §2 convention):
  0  the reading was taken, whatever it found. It makes no judgement, so it
     has none to fail on -- a report may not fail closed (ADR 0195)
  2  invalid operator input
  3  the reading could not be taken: this is not a git checkout, or this clone
     holds no tags at all. That is the opposite of failing closed -- it is
     refusing to print a clean answer it did not measure
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_postgres import REPO_ROOT, release_reading

#: Every `git` call this command makes is read-only and takes no operator value
#: as an argument. The one place a caller's string could reach `git` is a tag
#: name, and those come out of `git tag` itself.
_TIMEOUT = 20


def git(*arguments: str) -> str | None:
    """One `git` call, or `None` when it could not be answered.

    `None` rather than `""`: an empty answer is a real answer from several of
    these (`git tag --points-at HEAD` on an untagged commit), and folding the
    two together is how a value that was never read starts looking measured
    (D600, ADR 0195).
    """
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def lines(*arguments: str) -> tuple[str, ...]:
    """A `git` call whose answer is a list. Unreadable and empty both give ()."""
    output = git(*arguments)
    if not output:
        return ()
    return tuple(line for line in output.splitlines() if line)


def released_migrations(payload: str | None) -> int | None:
    """How many migrations a `released.lock.json` froze, or `None`.

    `None` for anything that is not a lock with a migration list: a release
    before the file existed reads as unknown rather than as zero.
    """
    if not payload:
        return None
    try:
        document = json.loads(payload)
    except (TypeError, ValueError):
        return None
    migrations = document.get("migrations") if isinstance(document, dict) else None
    if not isinstance(migrations, list):
        return None
    return len(migrations)


def observe() -> release_reading.Observation | None:
    """Measure the checkout. `None` when this is not a working tree at all."""
    head = git("rev-parse", "HEAD")
    if head is None:
        return None

    version_path = REPO_ROOT / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else ""

    tags = lines("tag")
    if not tags:
        return release_reading.Observation(head=head, version=version, tags=())

    #: A release is tagged when its VERSION is, not when HEAD is. `1.6.1`'s tag
    #: sits one commit past its own bump, and asking about HEAD would have
    #: called that release untagged for one commit and tagged for the next.
    version_tag = ""
    for tag in tags:
        if (git("show", f"{tag}:VERSION") or "") == version and version:
            version_tag = tag
            break

    last_tag = git("describe", "--tags", "--abbrev=0") or ""
    last_tag_commit = (git("rev-list", "-n1", last_tag) or "") if last_tag else ""
    last_tag_date = (git("log", "-1", "--format=%cI", last_tag) or "") if last_tag else ""
    last_tag_version = (git("show", f"{last_tag}:VERSION") or "") if last_tag else ""

    #: The window is measured from the tag carrying the tree's VERSION when
    #: there is one, and from the last reachable tag otherwise. In every
    #: ordinary case they are the same tag; when they are not, the sentence the
    #: reading prints and the count beneath it would otherwise name two
    #: different tags.
    window_tag = version_tag or last_tag
    since = git("rev-list", "--count", f"{window_tag}..HEAD") if window_tag else None
    commits_since_tag = int(since) if since and since.isdigit() else 0
    paths_since_tag = lines("diff", "--name-only", f"{window_tag}..HEAD") if window_tag else ()

    #: The commit that last moved VERSION -- the commit where the release is
    #: declared, and so the start of the window in which "does this belong
    #: inside the release" has a right answer.
    bump = lines("log", "-1", "--format=%H", "--", "VERSION")
    bump_commit = bump[0] if bump else ""
    bump_subject = (git("log", "-1", "--format=%s", bump_commit) or "") if bump_commit else ""
    bump_paths = (
        lines("diff", "--name-only", f"{bump_commit}~1", bump_commit) if bump_commit else ()
    )
    after_bump = git("rev-list", "--count", f"{bump_commit}..HEAD") if bump_commit else None
    commits_since_bump = int(after_bump) if after_bump and after_bump.isdigit() else 0
    paths_since_bump = lines("diff", "--name-only", f"{bump_commit}..HEAD") if bump_commit else ()

    lock = REPO_ROOT / "migrations" / "released.lock.json"
    return release_reading.Observation(
        head=head,
        version=version,
        tags=tags,
        tags_on_head=lines("tag", "--points-at", "HEAD"),
        last_tag=last_tag,
        last_tag_commit=last_tag_commit,
        last_tag_date=last_tag_date,
        last_tag_version=last_tag_version,
        version_tag=version_tag,
        window_tag=window_tag,
        commits_since_tag=commits_since_tag,
        paths_since_tag=paths_since_tag,
        bump_commit=bump_commit,
        bump_subject=bump_subject,
        bump_paths=bump_paths,
        commits_since_bump=commits_since_bump,
        paths_since_bump=paths_since_bump,
        released_migrations_at_tag=released_migrations(
            git("show", f"{last_tag}:migrations/released.lock.json") if last_tag else None
        ),
        released_migrations_in_tree=released_migrations(
            lock.read_text(encoding="utf-8") if lock.is_file() else None
        ),
        adrs_at_tag=len(
            [
                path
                for path in lines("ls-tree", "-r", "--name-only", last_tag, "--", "docs/decisions/")
                if Path(path).name[:1].isdigit()
            ]
        )
        if last_tag
        else None,
        adrs_in_tree=len(
            [
                path
                for path in sorted((REPO_ROOT / "docs" / "decisions").glob("[0-9]*.md"))
                if path.is_file()
            ]
        ),
    )


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()

    observation = observe()
    if observation is None:
        print(
            "release-reading: this is not a git checkout, so the reading cannot be taken.",
            file=sys.stderr,
        )
        return 3

    reading = release_reading.read(observation)
    for line in release_reading.render(reading):
        print(line)
    if reading.outcome == release_reading.NO_TAGS_IN_THIS_CLONE:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
