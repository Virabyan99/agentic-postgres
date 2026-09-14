"""`DX-WALK-001`'s operator half -- `apg dx-record` (ADR 0207 §3).

**The verb exists so that the walker and the sweep read the record the same
way.** A walker who could not run the check would be marked by a rubric they
never saw, inside the one claim that is about being told things that are not
written down. So the last proof here is the one that matters: the live proof
and this command must call the SAME functions, asserted against the source
rather than assumed from the fact that both were written on the same afternoon.

Every proof runs the product's own command (D1114), through the dispatcher, the
way README spells it.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, dx_record

pytestmark = [pytest.mark.contract, pytest.mark.p0]

APG = REPO_ROOT / "bin" / "apg.sh"
LIVE_PROOF = REPO_ROOT / "tests" / "deployment" / "test_session12_reuse.py"
SLUG = "walker"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "APG_PROJECT"}
    return subprocess.run(
        [str(APG), "dx-record", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def a_record_file(tmp_path: Path, **overrides: object) -> Path:
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
        "commands_run": ["bin/apg.sh dev up --project project.yaml"],
        "files_edited": [f"projects/{SLUG}/migrations/manifest.json", "project.yaml"],
        "documents_read": dx_record.digests(REPO_ROOT, list(dx_record.DOCUMENT_ROOTS)),
        "undocumented_steps": [],
        "reached_success_criterion": True,
    }
    document.update(overrides)
    path = tmp_path / "record.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def test_check_is_a_verb_and_reports_the_three_readings(tmp_path: Path) -> None:
    """Each reading printed as a list or as `none`, and `none` is not silence.

    A reading that printed nothing when it found nothing would be
    indistinguishable from a reading that did not run -- which is the shape this
    repository keeps producing, and the reason the word is there.
    """
    assert (
        "dx-record"
        in subprocess.run(
            [str(APG), "--list"], capture_output=True, text=True, check=True
        ).stdout.split()
    )

    clean = run("check", "--record", str(a_record_file(tmp_path)))
    assert clean.returncode == 0, clean.stdout + clean.stderr
    for reading in (
        "source edits: none",
        "commands the documentation does not name: none",
        "documents that moved after the walk: none",
        "followed_by: none",
    ):
        assert reading in clean.stdout, f"{reading!r} is not in the report:\n{clean.stdout}"

    edited = run(
        "check",
        "--record",
        str(a_record_file(tmp_path, files_edited=["migrations/manifest.json"])),
    )
    assert edited.returncode == 5, edited.stdout
    assert "source edits: 1" in edited.stdout and "migrations/manifest.json" in edited.stdout

    invented = run(
        "check",
        "--record",
        str(a_record_file(tmp_path, commands_run=["bin/apg.sh no-such-verb"])),
    )
    assert invented.returncode == 5
    assert "bin/no-such-verb.sh" in invented.stdout

    unreadable = run("check", "--record", str(tmp_path / "absent.json"))
    assert unreadable.returncode == 2, unreadable.stdout + unreadable.stderr

    short = tmp_path / "short.json"
    short.write_text(json.dumps({"release": "x"}), encoding="utf-8")
    incomplete = run("check", "--record", str(short))
    assert incomplete.returncode == 2
    assert "missing" in incomplete.stderr


def test_a_record_naming_a_document_this_checkout_lacks_is_exit_three(tmp_path: Path) -> None:
    """Exit 3 is *a missing local prerequisite*, and that is what this is.

    A document the record names and the checkout does not have says the reading
    is being made from the wrong checkout. Reporting it as a finding (5) would
    blame the walk for the reader's tree.
    """
    record = a_record_file(
        tmp_path,
        documents_read={"docs/this-was-never-here.md": "0" * 64},
    )
    result = run("check", "--record", str(record))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "docs/this-was-never-here.md" in result.stdout
    assert "wrong checkout" in result.stderr or "the checkout the walk" in result.stderr


def test_digest_writes_the_documents_read_member(tmp_path: Path) -> None:
    """The walker's one write, and it is the one nobody performs by hand.

    Four sha256 sums typed by a reader is a step the documentation would have
    to describe and would be got wrong -- and a wrong digest reads exactly like
    a document that moved, which sends the next reader to walk again.
    """
    record = a_record_file(tmp_path, documents_read={})
    result = run("digest", "--record", str(record))
    assert result.returncode == 0, result.stdout + result.stderr

    written = json.loads(record.read_text(encoding="utf-8"))["documents_read"]
    assert written, "digest wrote an empty member"
    for relative, value in written.items():
        assert (REPO_ROOT / relative).is_file(), f"digested a path that is not there: {relative}"
        assert len(value) == 64, f"{relative}'s digest is not a sha256: {value!r}"
        assert relative in result.stdout, f"{relative} was digested and not reported"

    # It must agree with the reader the sweep uses, or the walker is filling in
    # a field against a different definition from the one that will read it.
    assert written == dx_record.digests(REPO_ROOT, list(dx_record.DOCUMENT_ROOTS))

    after = run("check", "--record", str(record))
    assert "documents that moved after the walk: none" in after.stdout, after.stdout

    (tmp_path / "not-json.json").write_text("{", encoding="utf-8")
    assert run("digest", "--record", str(tmp_path / "not-json.json")).returncode == 2


def test_the_live_proof_calls_the_same_reader() -> None:
    """The command and the sweep must not be two implementations of one rule.

    §7's sixth question: who wrote the fixture, and do they share a belief with
    the code? Two readings that were written together and drift apart is the
    same failure one level up -- the walker's verdict would stop predicting the
    sweep's, and the walker is the one person who cannot check.

    So this reads `test_session12_reuse.py` with `ast`: the live proof calls
    `dx_record`'s functions by name, and the regex-and-basename reading it
    replaced is GONE rather than merely unused.
    """
    tree = ast.parse(LIVE_PROOF.read_text(encoding="utf-8"), filename=str(LIVE_PROOF))

    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name) and value.id == "dx_record":
                called.add(node.func.attr)

    for function in ("load", "source_edits", "unnamed_commands", "stale_documents"):
        assert function in called, (
            f"the live proof does not call dx_record.{function}; it is reading the record "
            f"some other way, and the walker's own check would stop predicting the sweep. "
            f"It calls: {sorted(called)}"
        )
    assert "followed_by_problems" in called, sorted(called)

    source = LIVE_PROOF.read_text(encoding="utf-8")
    assert "OPERATOR_INPUTS" not in source, (
        "the basename set is still in the live proof's module. The moved text has to go, not "
        "just stop being called (D1187) -- a second copy is a second definition"
    )
    assert "re.compile" not in source, (
        "the live proof still compiles a command regex of its own; the resolution belongs to "
        "dx_record so that both sides normalise the same way"
    )


def test_check_reads_blocked_by_and_prints_which_way_it_is_wrong(tmp_path: Path) -> None:
    """The reading reaches the OPERATOR and the walker, not only the library.

    A walker who cannot see the verdict a sweep will reach is being marked by a
    hidden rubric, which is this module's premise -- so a reading added to
    `dx_record` that the command does not print is half a repair, and the half
    that is missing is the half a walker can act on.

    The exit code does not move: a walk that did not reach the criterion is
    already exit 5. What moves is whether the report says where it stopped.
    """
    absent = run("check", "--record", str(a_record_file(tmp_path, reached_success_criterion=False)))
    assert absent.returncode == 5, absent.stdout + absent.stderr
    assert "blocked_by: 1" in absent.stdout, absent.stdout
    assert "blocked_by is absent" in absent.stdout, absent.stdout

    named = run(
        "check",
        "--record",
        str(
            a_record_file(
                tmp_path,
                reached_success_criterion=False,
                blocked_by="step 11: mcp-contract check exited 5 and no page says what to fix",
            )
        ),
    )
    assert named.returncode == 5, "a walk that did not finish is still a finding"
    assert "blocked_by: none" in named.stdout, named.stdout
    assert "the success criterion was not reached" in named.stdout, named.stdout

    # The control, in the same invocation: the clean record reports it clean.
    clean = run("check", "--record", str(a_record_file(tmp_path)))
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "blocked_by: none" in clean.stdout, clean.stdout
