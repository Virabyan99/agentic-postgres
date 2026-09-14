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
