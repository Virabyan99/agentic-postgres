"""Session 46's walk: a person who did not build this, from the site and an invitation link.

`DX-HOSTED-001` (claim `documented_path`, external). The record is
`APG_WALK_RECORD_FILE`: the person's own plain-text notes, typed into JSON by
the agent verbatim, read back and confirmed by the person (D2868) -- a
`path: "hosted"` record, read by `agentic_postgres.dx_record`'s hosted readers,
the same functions `apg dx-record check --path hosted` runs (ADR 0207 §3's rule:
the walker can see the verdict the sweep will reach).

Read against the site THIS checkout builds -- which, while the site is frozen
from the bump's push to the confirmation (D2883), is the site the person read
-- and against the published site itself, whose `apg-site-digest` meta must be
the record's. **The site is identified by its digest alone** (D2941, D2961): the
record's `site_commit` is not read against the checkout's history, because a
reading must not depend on where it ran (Run 9 read the same digest from a
docs commit that was not the external checkout's ancestor). The published
site's address is `site_build.SITE_URL`, never a second literal. **No SSH, no
process door** (D2174). Run 9 executed these proofs once (D2941).
"""

from __future__ import annotations

import ast
import os
import re
import urllib.request
from pathlib import Path

import pytest

from agentic_postgres import dx_record, site_build

pytestmark = [
    pytest.mark.p0,
    pytest.mark.external,
    pytest.mark.requires_environment("APG_WALK_RECORD_FILE"),
]

#: The published site (ADR 0283): the build's own constant, so the move to
#: `nomipg.com` (ADR 0299) moves this proof with it.
SITE = site_build.SITE_URL
#: The User-Agent every live read of the site sends (D2728: Pages refuses urllib's own).
USER_AGENT = "agentic-postgres-proof"
DIGEST_META = re.compile(r'<meta name="apg-site-digest" content="([0-9a-f]{64})">')


@pytest.fixture(scope="module")
def walk() -> dx_record.Record:
    """The record, loaded and shaped as the hosted path's; a malformed one fails
    here naming every problem."""
    record = dx_record.load(Path(os.environ.get("APG_WALK_RECORD_FILE", "")))
    assert record.document.get("path") == dx_record.HOSTED, record.document.get("path")
    shape = dx_record.shape_problems(record)
    assert not shape, shape
    return record


@pytest.fixture(scope="module")
def site() -> dx_record.HostedSite:
    return dx_record.hosted_site()


def test_a_person_who_did_not_build_this_reached_a_connection_string_from_the_site(
    walk: dx_record.Record, site: dx_record.HostedSite
) -> None:
    """ADR 0290 §4: a person (`kind: person`, holding the site, an invitation and
    the statement), the criterion reached -- the first goal, a working
    connection string -- no undocumented step, no file edited, and no finding
    from any hosted reading. A later goal the person did not reach is reported
    with their note and does not fail this by itself."""
    assert dx_record.followed_by_problems(walk) == []
    assert dx_record.blocked_by_problems(walk) == []
    assert walk.reached_success_criterion is True
    assert walk.undocumented_steps == [], walk.undocumented_steps
    assert walk.files_edited == []
    assert dx_record.hosted_problems(walk, site) == []
    stopped = [g for g in walk.document["goals"][1:] if g.get("reached") is False]
    print(f"goals after the first not reached: {[(g['goal'], g.get('note')) for g in stopped]}")


def test_the_record_names_the_deployed_site(
    walk: dx_record.Record, site: dx_record.HostedSite
) -> None:
    """The site the person read is the site this checkout builds (its digest)
    and the site published now (its meta) -- identified by the digest alone,
    never by where `site_commit` sits in this checkout's history (D2961); the
    release is the banner's."""
    assert walk.document["site_digest"] == site.digest, (walk.document["site_digest"], site.digest)
    request = urllib.request.Request(  # noqa: S310 -- the site's own name, https
        f"{SITE}/", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- the site's own name
        published = DIGEST_META.search(response.read().decode("utf-8"))
    assert published and published.group(1) == walk.document["site_digest"], (
        published.group(1) if published else None
    )
    assert walk.document["release"] == f"Release {site.version}"


def test_every_command_is_on_the_site(walk: dx_record.Record, site: dx_record.HostedSite) -> None:
    """ADR 0290 §3: every command typed is a line the site gives (an `apg`
    command by its noun, verb and flags), every page named is a page the site
    has. A person who typed no command and listed no page is admitted (D2961:
    the first person's record held both empty) -- what is NAMED must still be
    the site's."""
    assert dx_record.hosted_unnamed_commands(walk.commands_run, site) == []
    routes = walk.document["documents_read"]
    assert set(routes) <= site.routes, sorted(set(routes) - site.routes)


def test_the_walker_confirmed_the_record(walk: dx_record.Record) -> None:
    """D2868: the agent typed it (`transcribed_by.kind` agent), the person read
    it and said it is theirs after the walk (`confirmed_by_walker_at` not before
    `completed_at`), and it holds no secret."""
    assert walk.document["transcribed_by"]["kind"] == "agent"
    assert walk.document["confirmed_by_walker_at"] >= walk.document["completed_at"]
    assert dx_record.hosted_secrets(walk) == []


def test_this_module_uses_no_ssh() -> None:
    """D2174's rule for a customer proof: nothing here reaches the host but by
    its public names. Read from this file's own text and syntax."""
    text = Path(__file__).read_text(encoding="utf-8")
    for needle in ("para" + "miko", '"s' + 'sh"', "ss" + "h_destination", "ss" + "h-agent"):
        assert needle not in text, needle
    ast.parse(text)
