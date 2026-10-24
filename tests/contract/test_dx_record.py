"""`DX-WALK-001` -- the reader that decides `DX-001` (ADR 0207 §3).

**These are the proofs the old reading never had, because it never ran.** The
checks this module covers lived inside `test_session12_reuse.py` from Session 12
until Session 25, gated on `APG_DX_RECORD_FILE`, and no record was ever
declared -- so they were written, collected, and never executed against
anything. Rig 25d ran them for the first time, over a synthetic record of a
walker who had followed README exactly, and they refused it on seven files the
documentation had told them to create.

So each proof here is a pair: **a record the documentation produces must pass,
and a record that breaks the guarantee must fail naming the item.** One
direction alone is how the old reading stayed green.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, dx_record

pytestmark = [pytest.mark.contract, pytest.mark.p0]

SLUG = "walker"

#: Every file README's *Adding your own tables* and *Giving an agent your
#: tables* tell an adopter to create, read out of README rather than
#: remembered. Eight, and the plan's own list had seven: it omitted the
#: snapshot, README's row 4 (D1322).
TENANT_FILES = [
    f"projects/{SLUG}/migrations/templates/0001-tasks.sql",
    f"projects/{SLUG}/migrations/manifest.json",
    f"projects/{SLUG}/migrations/released.lock.json",
    f"projects/{SLUG}/contracts/postgrest-api-surface.yaml",
    f"projects/{SLUG}/contracts/postgrest-openapi.canonical.json",
    f"projects/{SLUG}/capabilities.yaml",
    f"projects/{SLUG}/contracts/mcp-capabilities.canonical.json",
    f"projects/{SLUG}/evaluation-cases.yaml",
]


def a_record(**overrides: object) -> dx_record.Record:
    """A walk that followed the documentation and needed nothing else."""
    document: dict[str, object] = {
        "followed_by": {
            "kind": "agent",
            "identity": "a model session",
            "instructed_by": "the operator",
            "context": "a clone of the release and the task statement, nothing else",
        },
        "completed_at": "2026-09-14T00:00:00Z",
        "release": "0000000",
        "project_slug": SLUG,
        "commands_run": [
            "bin/apg.sh doctor",
            "./deploy.sh --project project.yaml --capabilities capabilities.yaml --render-only",
            "bin/apg.sh dev up --project project.yaml",
            "bin/migrate.sh --project project.yaml freeze-lock",
            "bin/apg.sh generate --project project.yaml",
        ],
        "files_edited": [*TENANT_FILES, "project.yaml"],
        "documents_read": {},
        "undocumented_steps": [],
        "reached_success_criterion": True,
    }
    document.update(overrides)
    return dx_record.Record(path=Path("/dev/null"), document=document)


def test_a_walkers_own_project_directory_is_not_a_source_edit_and_a_release_file_is() -> None:
    """The repair D1304 names, in both directions and at the hard case.

    The hard case is `manifest.json`, which exists twice: the release's at
    `migrations/manifest.json` and the walker's at
    `projects/<slug>/migrations/manifest.json`. Compared by basename they are
    one string, which is why the old reading refused the walker's -- and would
    equally have accepted the release's if the walker had edited it.
    """
    assert dx_record.source_edits(a_record()) == [], (
        "a walker who followed README's two tenant sections exactly was told they had "
        "edited files this repository ships"
    )

    edited_release = a_record(files_edited=[*TENANT_FILES, "migrations/manifest.json"])
    assert dx_record.source_edits(edited_release) == ["migrations/manifest.json"], (
        "the release's migration manifest was edited and the reading did not say so"
    )

    both = a_record(
        files_edited=[
            f"projects/{SLUG}/migrations/manifest.json",
            "migrations/manifest.json",
        ]
    )
    assert dx_record.source_edits(both) == ["migrations/manifest.json"], (
        "the two files named `manifest.json` are not being told apart, which is the whole of D1304"
    )

    # An operator input is theirs at the ROOT and nowhere else: a widening that
    # accepted the basename anywhere would accept `contracts/capabilities.yaml`.
    assert dx_record.source_edits(a_record(files_edited=["capabilities.yaml"])) == []
    assert dx_record.source_edits(a_record(files_edited=["contracts/capabilities.yaml"])) == [
        "contracts/capabilities.yaml"
    ]

    # Another project's directory is not the walker's.
    assert dx_record.source_edits(
        a_record(files_edited=["projects/example/migrations/manifest.json"])
    ) == ["projects/example/migrations/manifest.json"]


def test_a_slug_cannot_widen_what_counts_as_the_walkers_own() -> None:
    """The slug becomes a path prefix, so it is validated before it is used.

    `bin/apg.sh` validates a verb before it becomes a path component for the
    same reason and says so in its header: a check that built the path first
    and tested afterwards would be relying on nothing accidentally being there.
    """
    for hostile in ("../..", "..", "", "a/b", "A", "-x"):
        record = a_record(project_slug=hostile, files_edited=["migrations/manifest.json"])
        assert "project_slug" in " ".join(dx_record.shape_problems(record)), (
            f"the slug {hostile!r} was accepted"
        )
        assert dx_record.source_edits(record) == ["migrations/manifest.json"], (
            f"the slug {hostile!r} excluded a release file from the reading"
        )

    # **The path the hostile prefix would actually swallow.** The battery found
    # this: dropping the validation left the loop above green, because
    # `migrations/manifest.json` does not begin with `projects/../` either way.
    # The reading only changes for a path written THROUGH the traversal, which
    # is what a record claiming a release edit as its own would look like.
    traversal = a_record(
        project_slug="..",
        files_edited=["projects/../migrations/manifest.json"],
    )
    assert dx_record.source_edits(traversal) == ["projects/../migrations/manifest.json"], (
        "a slug of `..` made `projects/../migrations/manifest.json` count as the walker's "
        "own directory. The slug becomes a prefix, so it is checked before it becomes one"
    )


def test_a_verb_typed_through_the_dispatcher_resolves_to_its_script_on_both_sides() -> None:
    """D1305 and D1323 -- the check was wrong in both directions at once.

    `bin/apg.sh no-such-verb` reduced to `bin/apg.sh`, which README names, so
    any verb passed. And `bin/dev.sh up`, which is how `docs/new-team-member.md`
    spells it, was refused, because that scan never read that guide.
    """
    assert dx_record.normalise("bin/apg.sh dev") == "bin/dev.sh"
    assert dx_record.normalise("bin/dev.sh") == "bin/dev.sh"
    assert dx_record.normalise("bin/apg.sh deploy") == "deploy.sh"
    assert dx_record.normalise("./deploy.sh") == "deploy.sh"

    documented = dx_record.documented_commands(REPO_ROOT)
    assert documented, "no documented commands were found, so this comparison is vacuous"
    assert "bin/dev.sh" in documented, (
        "the documentation names `apg dev` and the scan cannot see it as bin/dev.sh"
    )

    assert dx_record.unnamed_commands(a_record(), documented) == []

    both_spellings = a_record(
        commands_run=["bin/dev.sh up --project project.yaml", "bin/apg.sh dev up"]
    )
    assert dx_record.unnamed_commands(both_spellings, documented) == [], (
        "the two spellings of one command are not being resolved to one script"
    )

    invented = a_record(commands_run=["bin/apg.sh no-such-verb"])
    assert dx_record.unnamed_commands(invented, documented) == ["bin/no-such-verb.sh"], (
        "a verb the documentation never names passed through the dispatcher's spelling"
    )

    assert "docs/new-team-member.md" in dx_record.DOCUMENT_ROOTS, (
        "the guide that IS the documented path is not in the scanned set (D1323)"
    )


def test_a_document_that_moved_after_the_walk_is_named(tmp_path: Path) -> None:
    """D1306. A walk measures documents at a commit, or it measures nothing.

    An absent document is a DIFFERENT answer from a moved one and is reported
    separately: moved means walk again or say why, absent means the reading is
    being made from the wrong checkout.
    """
    (tmp_path / "README.md").write_text("one\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("two\n", encoding="utf-8")

    computed = dx_record.digests(tmp_path, ["README.md", "docs/README.md", "docs/gone.md"])
    assert set(computed) == {"README.md", "docs/README.md"}, (
        "a path that does not exist was given a digest rather than left out (D600)"
    )

    walked = a_record(documents_read=computed)
    assert dx_record.stale_documents(walked, tmp_path) == []
    assert dx_record.absent_documents(walked, tmp_path) == []

    (tmp_path / "README.md").write_text("one, corrected\n", encoding="utf-8")
    moved = dx_record.stale_documents(walked, tmp_path)
    assert len(moved) == 1 and moved[0].startswith("README.md"), moved

    (tmp_path / "docs" / "README.md").unlink()
    assert dx_record.absent_documents(walked, tmp_path) == ["docs/README.md"]
    assert not any("docs/README.md" in item for item in dx_record.stale_documents(walked, tmp_path))


def test_followed_by_must_be_structured() -> None:
    """ADR 0207 §1. The field that decides whether the walk counts.

    `context` must NAME the clone and the statement rather than merely exist:
    "a fresh session" is a sentence that is equally true of a session holding
    the whole `docs/plans/` directory, which is the one context ADR 0207
    excludes by name.
    """
    assert dx_record.followed_by_problems(a_record()) == []

    prose = dx_record.followed_by_problems(a_record(followed_by="a fresh session"))
    assert len(prose) == 1 and "not an object" in prose[0], prose

    for field in dx_record.FOLLOWED_BY_FIELDS:
        partial = {
            key: "x" if key != "context" else "a clone and the task statement"
            for key in dx_record.FOLLOWED_BY_FIELDS
            if key != field
        }
        problems = dx_record.followed_by_problems(a_record(followed_by=partial))
        assert any(field in problem for problem in problems), (
            f"a record with no followed_by.{field} was accepted: {problems}"
        )

    wrong_kind = a_record(
        followed_by={
            "kind": "committee",
            "identity": "x",
            "instructed_by": "y",
            "context": "a clone and the task statement",
        }
    )
    assert any("kind" in problem for problem in dx_record.followed_by_problems(wrong_kind))

    vague = a_record(
        followed_by={
            "kind": "agent",
            "identity": "x",
            "instructed_by": "y",
            "context": "a fresh session with no prior knowledge",
        }
    )
    problems = dx_record.followed_by_problems(vague)
    assert any("clone" in problem for problem in problems), (
        f"a context that does not name the clone was accepted: {problems}"
    )


def test_every_reader_is_total_over_a_malformed_record(tmp_path: Path) -> None:
    """A record is written by somebody who has never seen this repository.

    The useful answer to a list where a dict belongs is a named problem, not a
    `TypeError` four frames down in a sweep the operator is watching.
    """
    broken = a_record(
        commands_run="bin/apg.sh dev up",
        files_edited={"a": 1},
        documents_read=[],
        undocumented_steps=None,
        reached_success_criterion="yes",
    )
    assert dx_record.source_edits(broken) == []
    assert dx_record.unnamed_commands(broken, {"bin/dev.sh"}) == []
    assert dx_record.stale_documents(broken, REPO_ROOT) == []
    assert dx_record.absent_documents(broken, REPO_ROOT) == []
    problems = dx_record.shape_problems(broken)
    for field in ("commands_run", "files_edited", "documents_read", "reached_success_criterion"):
        assert any(field in problem for problem in problems), (field, problems)


def test_load_tells_absent_from_incomplete(tmp_path: Path) -> None:
    """ADR 0195's three outcomes, at the front door.

    An operator sent to look for a missing file when the file is there and short
    a field looks in the wrong place.
    """
    with pytest.raises(dx_record.RecordUnreadable):
        dx_record.load(tmp_path / "nothing.json")

    not_json = tmp_path / "bad.json"
    not_json.write_text("{", encoding="utf-8")
    with pytest.raises(dx_record.RecordUnreadable):
        dx_record.load(not_json)

    a_list = tmp_path / "list.json"
    a_list.write_text("[]", encoding="utf-8")
    with pytest.raises(dx_record.RecordUnreadable):
        dx_record.load(a_list)

    short = tmp_path / "short.json"
    short.write_text(json.dumps({"release": "x"}), encoding="utf-8")
    with pytest.raises(dx_record.RecordIncomplete) as raised:
        dx_record.load(short)
    for field in dx_record.REQUIRED_FIELDS:
        if field != "release":
            assert field in str(raised.value), f"{field} was not named as missing"

    whole = tmp_path / "whole.json"
    whole.write_text(json.dumps(a_record().document), encoding="utf-8")
    assert dx_record.load(whole).project_slug == SLUG


def test_a_failed_walk_must_say_where_it_stopped() -> None:
    """`blocked_by` gets a reader on the day the task statement asks for it.

    ADR 0207 §1's statement tells a walker to write `blocked_by` when the
    success criterion was not reached. A declared field with no reader is an
    unverified field, and this repository has paid for that three times (D816,
    D929, D1247) -- so the field is read rather than merely collected. A failed
    walk that does not say WHERE it stopped tells the builder the path is broken
    and nothing about where, and §9 allows at most two walks: the second one
    should be spent on a repair, not on a search.

    Five arms. The fourth and fifth are what make this more than a presence
    check: a named blocker is accepted, and a record that reached the criterion
    while carrying a blocker has two halves that disagree -- reading only the
    reassuring one is what §7 warns about.
    """
    # The control: a walk that finished and says nothing about being blocked.
    assert dx_record.blocked_by_problems(a_record()) == []

    absent = a_record(reached_success_criterion=False)
    problems = dx_record.blocked_by_problems(absent)
    assert problems and "blocked_by is absent" in problems[0], problems

    empty = a_record(reached_success_criterion=False, blocked_by="   ")
    assert dx_record.blocked_by_problems(empty), "an empty sentence was accepted"

    named = a_record(
        reached_success_criterion=False,
        blocked_by="step 9: freeze-lock exited 5 and no page says what to re-stamp",
    )
    assert dx_record.blocked_by_problems(named) == [], "a named blocker was refused"

    contradictory = a_record(blocked_by="step 9 refused me")
    problems = dx_record.blocked_by_problems(contradictory)
    assert problems and "success criterion was reached" in problems[0], problems


# ---------------------------------------------------------------------------
# What the command scan can and cannot see (D464, D1422)
# ---------------------------------------------------------------------------


def test_the_command_scan_reads_a_script_and_never_a_flag() -> None:
    """The stated limit, measured, so it is a property rather than a sentence.

    `dx_record._COMMAND` is a text scan. The ledger has carried two descriptions
    of what it misses -- *"a text scan rather than a parser"* (D464) and *"a
    flag on a backslash-continuation line is unchecked"* -- and the second
    understates it: **no flag on any line is read**, continuation or not. A
    repair aimed at continuations would have left the scan reading no flags and
    looked like progress (D1422).

    So the limit is asserted in both directions. What it MUST see is every
    spelling the documentation actually uses; what it must be known NOT to see
    is every flag, because a caller who believes otherwise will write a proof
    that compares a flag against nothing.

    **Not a parser.** The direction of this limit is the safe one: an unmatched
    documented command makes a walker's honest use look undocumented, which
    over-reports gaps rather than hiding them.
    """
    seen = dx_record._commands_in

    # Seen: the three spellings, in the four shapes the documentation uses.
    assert seen("Run `bin/migrate.sh` first.") == {"bin/migrate.sh"}
    assert seen("```bash\n./deploy.sh --render-only\n```") == {"deploy.sh"}
    assert seen("bin/apg.sh dev up") == {"bin/dev.sh"}
    assert seen("(bin/render-jwks.py)") == {"bin/render-jwks.py"}
    assert seen("  sudo bin/doctor.sh --project x") == {"bin/doctor.sh"}

    # `bin/apg.sh deploy` reduces to the script the release actually ships.
    assert seen("bin/apg.sh deploy") == {"deploy.sh"}

    # NOT seen, and each of these is a thing a caller might assume:
    #   a flag, on the same line as its command
    assert seen("bin/migrate.sh --project p freeze-lock --follows 20260904120030") == {
        "bin/migrate.sh"
    }
    #   a flag on a backslash continuation -- the ledger's narrower claim
    assert seen("bin/upgrade.sh check \\\n  --project alpha \\\n  --json") == {"bin/upgrade.sh"}
    #   a verb that is not `apg.sh`'s
    assert seen("bin/migrate.sh freeze-lock") == {"bin/migrate.sh"}
    #   a bare command with no `bin/` prefix and no `./`
    assert seen("deploy.sh --render-only") == set()
    assert seen("apg-diag catalog alpha migration-ledger") == set()
    #   an environment variable in front of it
    assert seen("APG_PROJECT=alpha bin/apg.sh dev up") == {"bin/dev.sh"}

    # And it cannot tell prose from a shell block: the same string matches in
    # both, which is what makes a mention anywhere count as documentation.
    assert seen("The `bin/backup.sh` command is not run by hand.") == {"bin/backup.sh"}

    # The one thing the scan is allowed to be strict about: an unknown verb
    # after `apg.sh` reduces to a script, and that script is compared against
    # what the release ships -- so a verb the documentation invents has nowhere
    # to hide (`normalise`'s own docstring, D1305/D1323).
    assert dx_record.normalise("bin/apg.sh no-such-verb") == "bin/no-such-verb.sh"


# ---------------------------------------------------------------------------
# Session 46 (ADR 0290, D2867): the hosted record -- a person, the site, an
# invitation link. The clone path above is untouched; these read the second.
# ---------------------------------------------------------------------------

HOSTED_GOALS = ("connect", "your own SQL", "a branch", "usage", "slowest queries", "support page")
HOSTED_LINES = (
    "pipx install agentic-postgres-cli",
    "apg login password --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME",
    "apg project claim --project-key KEY --token-file FILE",
    "apg project diagnostics --project-key KEY --output ./support.json",
)


def _hosted_site() -> Any:
    """A site of five routes and four documented lines -- built per call, so a
    reader that is absent fails the test that asks for it, not the module."""
    return dx_record.HostedSite(
        digest="d" * 64,
        version="1.24.0",
        routes=frozenset({"/", "/quickstart/", "/docs/", "/docs/connecting/", "/docs/projects/"}),
        lines=HOSTED_LINES,
        goals=HOSTED_GOALS,
    )


def _goals(**reached: bool) -> list[dict[str, object]]:
    goals: list[dict[str, object]] = []
    for name in HOSTED_GOALS:
        done = reached.get(name.replace(" ", "_"), True)
        goal: dict[str, object] = {
            "goal": name,
            "reached": done,
            "at": "2026-10-30T10:40:00Z" if done else None,
        }
        if not done:
            goal["note"] = "stopped here"
        goals.append(goal)
    return goals


def a_hosted_record(**overrides: object) -> dx_record.Record:
    """A person who walked the site from an invitation link and needed nothing else."""
    document: dict[str, object] = {
        "path": "hosted",
        "followed_by": {
            "kind": "person",
            "identity": "a recruited reader",
            "instructed_by": "the operator",
            "context": "the site's URL, an account invitation link and the statement, nothing else",
        },
        "started_at": "2026-10-30T10:00:00Z",
        "completed_at": "2026-10-30T11:30:00Z",
        "release": "Release 1.24.0",
        "site_commit": "a" * 40,
        "site_digest": "d" * 64,
        "documents_read": ["/", "/quickstart/", "/docs/connecting/"],
        "commands_run": [],
        "files_edited": [],
        "goals": _goals(),
        "timeline": {
            "link_opened": "2026-10-30T10:00:00Z",
            "account_created": "2026-10-30T10:03:00Z",
            "factor_enrolled": "2026-10-30T10:06:00Z",
            "organization_created": "2026-10-30T10:05:00Z",
            "creation_accepted": "2026-10-30T10:08:00Z",
            "connection_string": None,
        },
        "undocumented_steps": [],
        "reached_success_criterion": True,
        "transcribed_by": {"kind": "agent", "identity": "the executor's session"},
        "confirmed_by_walker_at": "2026-10-31T09:00:00Z",
    }
    document.update(overrides)
    return dx_record.Record(path=Path("/dev/null"), document=document)


def _all_findings(record: dx_record.Record) -> list[str]:
    return [
        *dx_record.shape_problems(record),
        *dx_record.followed_by_problems(record),
        *dx_record.blocked_by_problems(record),
        *dx_record.hosted_problems(record, _hosted_site()),
    ]


def test_a_hosted_record_the_site_produces_is_clean() -> None:
    """The control for everything below: a person's record, every route a built
    route, a browser-only walk (no command), every goal reached, transcribed by
    the agent and confirmed after the walk -- no finding from any reader. A
    command the site gives, with its own values, is also clean."""
    assert _all_findings(a_hosted_record()) == []
    typed = a_hosted_record(
        commands_run=[
            "pipx install  agentic-postgres-cli",
            "apg project claim --project-key slot10-prod --token-file /home/p/token",
        ]
    )
    assert _all_findings(typed) == []


def test_the_clone_path_is_read_as_before_and_an_unknown_path_is_a_shape_problem(
    tmp_path: Path,
) -> None:
    """ADR 0290 §1: no `path` is the clone walk, loaded and shaped exactly as
    ADR 0207 reads it; `hosted` needs its own fields (an absent one named,
    never assumed); any other `path` is a shape problem."""
    clone = a_record()
    assert "path" not in clone.document
    assert dx_record.shape_problems(clone) == []
    hosted = tmp_path / "hosted.json"
    document = dict(a_hosted_record().document)
    del document["confirmed_by_walker_at"]
    hosted.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(dx_record.RecordIncomplete, match="confirmed_by_walker_at"):
        dx_record.load(hosted)
    elsewhere = a_hosted_record(path="elsewhere")
    assert any("path is 'elsewhere'" in p for p in dx_record.shape_problems(elsewhere))


def test_a_hosted_walker_is_a_person_holding_the_site_an_invitation_and_the_statement() -> None:
    """ADR 0290 §2, §6: `kind` must be `person` -- an agent's or a driver's walk
    does not count for this path -- and `context` names the site, the
    invitation and the statement (it need not name a clone)."""
    agent = a_hosted_record(
        followed_by={**a_hosted_record().document["followed_by"], "kind": "agent"}  # type: ignore[dict-item]
    )
    assert any("must be 'person'" in p for p in dx_record.followed_by_problems(agent))
    vague = a_hosted_record(
        followed_by={  # type: ignore[dict-item]
            **a_hosted_record().document["followed_by"],
            "context": "the site and the statement",
        }
    )
    assert any("invitation" in p for p in dx_record.followed_by_problems(vague))
    assert dx_record.followed_by_problems(a_hosted_record()) == []


def test_the_site_read_is_the_site_built_here() -> None:
    """ADR 0290 §3, the site and the routes: another build's digest is *the
    site moved after the walk*; a route the build does not produce is named,
    never dropped; the release must be the banner this checkout prints."""
    moved = dx_record.hosted_problems(a_hosted_record(site_digest="e" * 64), _hosted_site())
    assert any("the site moved after the walk" in p for p in moved), moved
    wrong = dx_record.hosted_problems(
        a_hosted_record(documents_read=["/", "/docs/nowhere/"]), _hosted_site()
    )
    assert any("/docs/nowhere/" in p for p in wrong), wrong
    older = dx_record.hosted_problems(a_hosted_record(release="Release 1.23.0"), _hosted_site())
    assert any("Release 1.23.0" in p for p in older), older


def test_a_command_matches_a_site_line_by_noun_verb_and_flags() -> None:
    """ADR 0290 §3, the commands: an `apg` command matches a documented line
    with its `apg <noun> <verb>` and every flag it used, values free; a flag no
    line gives, or a verb no line gives, is unnamed; any other command matches
    a documented line after whitespace is normalised."""

    def unnamed(*commands: str) -> list[str]:
        return dx_record.hosted_unnamed_commands(list(commands), _hosted_site())

    assert unnamed("apg project claim --project-key slot10-prod --token-file ~/token") == []
    assert unnamed("apg project claim --project-key=slot10-prod --token-file=~/token") == []
    assert unnamed("apg project claim --project-key slot10-prod --force") == [
        "apg project claim --project-key slot10-prod --force"
    ]
    assert unnamed("apg project nuke --project-key slot10-prod") != []
    assert unnamed("pipx install agentic-postgres-cli") == []
    assert unnamed("curl https://agenticpostgresql.com") != []
    findings = dx_record.hosted_problems(
        a_hosted_record(commands_run=["apg project nuke --project-key K"]), _hosted_site()
    )
    assert any("apg project nuke" in p for p in findings), findings


def test_no_secret_reaches_the_record_and_none_is_echoed() -> None:
    """ADR 0290 §3, no secret: a connection string with a password, an
    invitation link, an otpauth URI and a 43-character base64url run are each
    refused where they sit -- named by their place, the value never printed.
    The control: a site commit (40 hex) and digest (64 hex) are not tokens."""
    planted = {
        "postgresql://u:hunter2-pass@pool.example:5432/db": "a connection string",
        "https://control.example/accept#tok": "an invitation link",
        "otpauth://totp/x?secret=ABC": "an otpauth URI",
        "k" * 43: "a 43-character",
    }
    for value, said in planted.items():
        goals = _goals()
        goals[2]["note"] = f"I used {value}"
        findings = dx_record.hosted_problems(a_hosted_record(goals=goals), _hosted_site())
        hits = [p for p in findings if "goals[2].note" in p]
        assert hits and said in hits[0], (said, findings)
        assert value not in " ".join(findings), "a secret was echoed"
    assert dx_record.hosted_problems(a_hosted_record(), _hosted_site()) == []


def test_the_hands_are_the_persons_and_the_transcribers() -> None:
    """ADR 0290 §3, the hands, and D2868: the agent transcribes, the person
    confirms -- and the confirmation comes after the walk ended. A file edited
    is a finding on this path, whatever it was."""
    by_person = a_hosted_record(transcribed_by={"kind": "person", "identity": "x"})
    assert any("transcribed_by" in p for p in dx_record.hosted_problems(by_person, _hosted_site()))
    early = a_hosted_record(confirmed_by_walker_at="2026-10-30T11:00:00Z")
    assert any(
        "confirmed_by_walker_at" in p for p in dx_record.hosted_problems(early, _hosted_site())
    )
    edited = a_hosted_record(files_edited=["site/pages/quickstart.md"])
    assert any(
        "edits no product file" in p for p in dx_record.hosted_problems(edited, _hosted_site())
    )


def test_the_goals_are_the_statements_in_its_order() -> None:
    """ADR 0290 §2, §4: the goals are the statement's six, in its order, read
    from `docs/hosted-walk.md` itself; the criterion is the first goal; a goal
    not reached carries the person's note, and a later goal not reached is not
    by itself a finding. The control: the statement's own list is six names."""
    assert dx_record.statement_goals(REPO_ROOT) == HOSTED_GOALS
    swapped = _goals()
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert any(
        "goals" in p
        for p in dx_record.hosted_problems(a_hosted_record(goals=swapped), _hosted_site())
    )
    disagree = a_hosted_record(reached_success_criterion=False, blocked_by="the creation failed")
    assert any(
        "reached_success_criterion" in p
        for p in dx_record.hosted_problems(disagree, _hosted_site())
    )
    silent = _goals(usage=False)
    del silent[3]["note"]
    assert any("note" in p for p in dx_record.shape_problems(a_hosted_record(goals=silent)))
    stopped = a_hosted_record(goals=_goals(support_page=False))
    assert _all_findings(stopped) == []


def test_the_site_at_this_checkout_is_what_the_reader_reads() -> None:
    """`hosted_site()` is the site this checkout builds: its digest is
    `site_build.digest()`, its routes the pages' routes, its lines include a
    command the quickstart gives, its version the VERSION file."""
    from agentic_postgres import site_build

    site = dx_record.hosted_site()
    assert site.digest == site_build.digest()
    assert site.routes == frozenset(page.route for page in site_build.pages())
    assert "pipx install agentic-postgres-cli" in site.lines
    assert site.version == (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert site.goals == dx_record.statement_goals(REPO_ROOT)


def test_every_hosted_reader_is_total_over_a_malformed_record() -> None:
    """A list where an object belongs, a string where a list does: each reader
    names it and returns, never a `TypeError` (the module's rule)."""
    broken = a_hosted_record(
        goals="all of them",
        timeline=["x"],
        documents_read="/",
        commands_run="apg",
        transcribed_by="me",
        followed_by=["person"],
        site_digest=7,
    )
    assert dx_record.shape_problems(broken)
    assert dx_record.followed_by_problems(broken)
    dx_record.hosted_problems(broken, _hosted_site())
