"""`REL-COMPAT-001`, offline half: the command refuses before it writes anything.

**Two assertions per refusal, and the second is the one that is easy to leave
out.** That a command exits non-zero says it refused. It does not say it refused
*before* changing something -- and "no mutation before a plan is produced" is the
whole guarantee. So every refusal below is checked against a digest of the tree
taken before it ran.

`bin/upgrade.py`'s behaviour is exercised through `bin/upgrade.sh`, the way an
operator reaches it, rather than by importing `main()`. ADR 0065/0066: a proof
that reaches the right end state by a route the product does not take proves the
end state is reachable, not that the product reaches it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMMAND = REPO_ROOT / "bin" / "upgrade.sh"

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3
EXIT_MISSING = 4
EXIT_BLOCKED = 6


def rendered(**overrides: object) -> dict:
    document = {
        "document_kind": "rendered",
        "schema_version": 13,
        "template_version": "0.1.0-dev",
        "inputs": {
            "project_sha256": "a" * 64,
            "capabilities_sha256": "b" * 64,
            "secrets_contract_sha256": "c" * 64,
            "versions_lock_sha256": "d" * 64,
            "source_specification_sha256": "e" * 64,
        },
        "secrets": {"required_names": ["one"]},
    }
    document.update(overrides)
    return document


def write(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def tree_digest() -> str:
    """A digest of everything this command could plausibly write.

    `.generated/` is the only place in a checkout a render lands, and it is what
    `deploy.sh --render-only` writes. Names, sizes and mtimes rather than
    contents: cheap, and it changes on a rewrite that happens to produce
    identical bytes -- which is the case a content digest would miss.
    """
    root = REPO_ROOT / ".generated"
    parts = []
    for path in sorted(root.rglob("*")):
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append(f"{path.relative_to(root)}:{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(COMMAND), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def refuses_without_writing(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run, and assert the tree is byte-for-byte what it was."""
    before = tree_digest()
    result = run(*arguments)
    assert tree_digest() == before, (
        f"`upgrade.sh {' '.join(arguments)}` changed .generated/. "
        "This command must produce a plan without mutating anything."
    )
    return result


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_an_insufficient_bump_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    """A patch bump cannot carry a migration (ADR 0162)."""
    installed = write(tmp_path / "installed.json", rendered(template_version="1.0.0"))
    candidate = write(tmp_path / "candidate.json", rendered(template_version="1.0.1"))

    result = refuses_without_writing(
        "plan",
        "--project",
        "fixture-alpha-dev",
        "--installed",
        str(installed),
        "--candidate",
        str(candidate),
        "--also",
        "migration_added",
    )
    assert result.returncode == EXIT_BLOCKED, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "require minor" in result.stdout


def test_a_moved_operator_input_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    """An upgrade changes the release, not the manifests the operator supplies."""
    candidate_document = rendered(template_version="0.2.0")
    candidate_document["inputs"]["project_sha256"] = "9" * 64

    installed = write(tmp_path / "installed.json", rendered())
    candidate = write(tmp_path / "candidate.json", candidate_document)

    result = refuses_without_writing(
        "plan", "--project", "x", "--installed", str(installed), "--candidate", str(candidate)
    )
    assert result.returncode == EXIT_BLOCKED
    assert "the operator's own inputs moved" in result.stdout


def test_a_deployed_document_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    """D732/D733. The kinds are not comparable and the command says so."""
    installed = write(tmp_path / "installed.json", rendered(document_kind="deployed"))
    candidate = write(tmp_path / "candidate.json", rendered(template_version="0.2.0"))

    result = refuses_without_writing(
        "plan", "--project", "x", "--installed", str(installed), "--candidate", str(candidate)
    )
    assert result.returncode == EXIT_BLOCKED
    assert "not 'rendered'" in result.stdout


def test_a_missing_candidate_refuses_rather_than_rendering_one(tmp_path: Path) -> None:
    """The command writes nothing, so it does not render its own candidate.

    A planner that rendered would write `.generated/<key>` -- which is a
    mutation, in the one command whose contract is that it performs none.
    """
    installed = write(tmp_path / "installed.json", rendered())

    result = refuses_without_writing("plan", "--project", "x", "--installed", str(installed))
    assert result.returncode == EXIT_INPUT
    assert "renders nothing" in result.stderr


def test_check_reports_what_the_state_root_actually_permits() -> None:
    """ADR 0157's distinction, asserted against the root the machine has.

    "Not deployed here" and "you may not look" are different answers, and only
    one of them is a fact about the deployment.

    **This asserted exit 3 unconditionally, and that was a description of the
    developer's workstation** (D876). `/var/lib/agentic-postgres` is
    `drwx------ root root` here, left by a deploy in August, so `check` answers
    *"cannot tell"*. On a machine that has never deployed anything the directory
    is **absent**, `check` answers `UNDETERMINED` with *"nobody looked"* -- also
    correct, also ADR 0157 -- and the assertion demanded the wrong one. It went
    red on a runner the first time CI ever got far enough to run it.

    So it now asserts the **mapping**: whichever state the root is in, the code
    and the message must be the ones that state calls for. That is falsifiable on
    both machines, and it reaches a branch that until now was chosen by accident
    -- neither environment had ever run the other's.
    """
    root = Path("/var/lib/agentic-postgres/rendered")
    try:
        unreadable = root.exists() and not os.access(root, os.R_OK | os.X_OK)
    except PermissionError:
        # ADR 0157's distinction, arriving in this test's own inspection: the
        # PARENT is `drwx------ root root`, so even asking whether the rendered
        # root exists is refused. "Cannot look" is what that is.
        unreadable = True

    result = refuses_without_writing("check", "--project", "no-such-project-anywhere")
    output = result.stdout + result.stderr

    # The control: the two answers are different codes, so an implementation
    # returning one of them always fails one branch of this test wherever it runs.
    assert EXIT_PREREQUISITE != EXIT_MISSING

    if unreadable:
        assert result.returncode == EXIT_PREREQUISITE, output
        assert "cannot tell whether" in result.stderr
        assert "not the same as the project not being deployed" in result.stderr
    else:
        assert result.returncode == EXIT_MISSING, output
        assert "nothing installed for no-such-project-anywhere" in output
        assert "nobody looked" in output, (
            "the command reports absence without saying it looked, which is the "
            "claim ADR 0157 refuses"
        )


def test_a_supplied_installed_path_that_does_not_exist_is_missing(tmp_path: Path) -> None:
    """The other side of the same coin: readable, and genuinely not there."""
    result = refuses_without_writing(
        "check", "--project", "x", "--installed", str(tmp_path / "nothing.json")
    )
    assert result.returncode == EXIT_MISSING, result.stdout + result.stderr
    assert "no installed rendered document" in result.stderr


# ---------------------------------------------------------------------------
# The shape of the surface
# ---------------------------------------------------------------------------


def test_an_unknown_verb_is_refused() -> None:
    result = refuses_without_writing("destroy", "--project", "x")
    assert result.returncode == EXIT_INPUT
    assert "unknown verb" in result.stderr


def test_no_verb_writes_even_on_the_happy_path(tmp_path: Path) -> None:
    """The permitted case must not mutate either, and that is the one a reader
    would assume is safe without checking."""
    installed = write(tmp_path / "installed.json", rendered(template_version="1.0.0"))
    candidate = write(tmp_path / "candidate.json", rendered(template_version="1.1.0"))

    result = refuses_without_writing(
        "plan",
        "--project",
        "x",
        "--installed",
        str(installed),
        "--candidate",
        str(candidate),
        "--also",
        "migration_added",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing blocks this upgrade" in result.stdout
    assert "deploy.sh --through-session" in result.stdout


def test_the_json_output_is_machine_readable_and_names_the_verdict(tmp_path: Path) -> None:
    installed = write(tmp_path / "installed.json", rendered())
    candidate = write(tmp_path / "candidate.json", rendered())

    result = refuses_without_writing(
        "plan",
        "--project",
        "x",
        "--installed",
        str(installed),
        "--candidate",
        str(candidate),
        "--json",
    )
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "blocked"
    assert payload["reasons"]
    assert payload["project"] == "x"


def test_the_tree_digest_would_notice_a_write(tmp_path: Path) -> None:
    """The control for every assertion above (D509).

    A digest that could not change would make `refuses_without_writing` a
    decoration on a plain `run`. So write into `.generated/` and confirm the
    digest moves.
    """
    before = tree_digest()
    probe = REPO_ROOT / ".generated" / "upgrade-command-control-probe"
    probe.write_text("planted by the control", encoding="utf-8")
    try:
        assert tree_digest() != before, "the tree digest does not notice a new file"
    finally:
        probe.unlink()
    assert tree_digest() == before, "the control did not clean up after itself"


def test_the_command_is_reached_the_way_an_operator_reaches_it() -> None:
    """ADR 0065/0066: every proof above invokes the shell entry point.

    Narrow on purpose. The first draft also asserted that `bin/` is not
    importable, so that no proof could take a route around `upgrade.sh` -- and
    `import bin` **succeeds**, because a directory with no `__init__.py` is a
    namespace package. The assertion was about Python's import system rather
    than about this module's route, and it would have passed for an unrelated
    reason on any tree where `bin/` happened to be unimportable (D374).

    What is checkable is that the entry point is the shell script and that it
    runs, which is what every test here goes through.
    """
    assert COMMAND.name.endswith(".sh")
    assert COMMAND.is_file()
    assert run("--help").returncode == 0
