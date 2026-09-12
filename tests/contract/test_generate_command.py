"""`GEN-CMD-001` (Session 23 Run 3 step 4).

The operator surface of the generator. Every proof here runs **the command**,
never a re-implementation of what it does (D1114, D1117): `api-contract.sh
--check --project` could not exit 0 for four sessions while its tests were
green, because the tests re-implemented the comparison instead of making it.

Two properties get most of the attention, because both have failed in this
repository before:

* **every argument error exits 2 before a file is read.** The shell wrapper
  decides them, so a malformed invocation cannot reach Python and produce a
  partially written directory.
* **`--check` writes nothing** -- asserted by comparing the directory's bytes
  and mtimes across the call, not by reading the code.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT

GENERATE = REPO_ROOT / "bin" / "generate.sh"
APG = REPO_ROOT / "bin" / "apg.sh"
PROJECT = "project.example.yaml"
CAPABILITIES = "capabilities.example.yaml"
#: The project that declares NO migration set (ADR 0198's control).
PROJECT_WITHOUT_SET = "project.second.example.yaml"
EXAMPLE_CLIENT = REPO_ROOT / "projects" / "example" / "clients" / "typescript"


def run(*arguments: str, command: Path = GENERATE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(command), *arguments], cwd=REPO_ROOT, capture_output=True, text=True, timeout=600
    )


# ---------------------------------------------------------------------------
# the wrapper: every argument error, before Python runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "why"),
    [
        ((), "no --project"),
        (("--project",), "--project with no value"),
        (("--project", "no-such-manifest.yaml"), "a manifest that is not there"),
        (("--project", PROJECT, "--project", PROJECT), "--project twice"),
        (("--project", PROJECT, "--out", "a", "--out", "b"), "--out twice"),
        (
            ("--project", PROJECT, "--capabilities", "no-such.yaml"),
            "a capability file that is not there",
        ),
        (("--project", PROJECT, "--unknown-flag"), "an unknown flag"),
        (("--project", PROJECT, "stray"), "a positional argument"),
        (("--out", "clients"), "--out with no --project"),
    ],
)
def test_every_argument_error_exits_two(arguments: tuple[str, ...], why: str) -> None:
    """**GEN-CMD-001.** Exit 2, and the message names what was wrong.

    Decided by the shell wrapper, so none of these reaches Python: an
    invocation that got as far as writing files and then refused would leave a
    half-generated directory, and the developer's next `--check` would compare
    against it.
    """
    done = run(*arguments)
    assert done.returncode == 2, (
        f"{why} exited {done.returncode}, not 2:\n{done.stdout}\n{done.stderr}"
    )
    assert done.stderr.startswith("generate: ") or "Usage:" in done.stderr, (
        f"{why} produced no message a reader could act on: {done.stderr!r}"
    )
    assert "Traceback" not in done.stderr, (
        f"{why} reached Python; the wrapper is meant to decide it first"
    )


def test_help_exits_zero_and_describes_the_four_init_answers() -> None:
    """**GEN-CMD-001.** `--help` is the one place the four outcomes are spelled out."""
    done = run("--help")
    assert done.returncode == 0
    for word in ("--project", "--capabilities", "--out", "--check"):
        assert word in done.stdout
    for outcome in ("stale_contract", "unreachable", "unparsable"):
        assert outcome in done.stdout, (
            f"--help does not mention {outcome}; the difference between them is the whole "
            "point of init() having more than two answers"
        )


def test_generate_is_a_verb_of_the_dispatcher() -> None:
    """**GEN-CMD-001.** `apg generate` reaches it, by the dispatcher's derivation.

    `bin/apg.sh` derives its verbs from `bin/*.sh` rather than from a list, so
    this needed no dispatcher edit -- and this proof is what says the derivation
    actually reached the new file rather than that somebody believed it would.
    """
    listed = run("--list", command=APG)
    assert listed.returncode == 0
    assert "generate" in listed.stdout.split(), f"apg --list does not offer it:\n{listed.stdout}"

    through = run("generate", "--help", command=APG)
    assert through.returncode == 0
    assert "Usage: bin/generate.sh" in through.stdout


def test_an_out_outside_the_checkout_is_refused() -> None:
    """**GEN-CMD-001.** A generated client is an artefact of its project.

    Writing one anywhere on the filesystem is not this command's business, and
    the refusal is exit 2 rather than a failure part-way through writing.
    """
    done = run("--project", PROJECT, "--capabilities", CAPABILITIES, "--out", "/etc/apg-probe")
    assert done.returncode == 2
    assert "outside this checkout" in done.stderr


def test_an_unrendered_project_is_refused_with_the_command_that_renders_it(
    tmp_path: Path,
) -> None:
    """**GEN-CMD-001.** Exit 4, naming the render this invocation needs (D975).

    The manifest lives OUTSIDE the checkout on purpose: `.gitignore` names the
    project manifests individually, so a third one inside the tree dirties the
    release and every deploy refuses it (D971).
    """
    manifest = tmp_path / "project.unrendered.yaml"
    source = (REPO_ROOT / PROJECT_WITHOUT_SET).read_text(encoding="utf-8")
    # A slug nothing has rendered. Changed only here, so every other field is
    # the committed control's and the refusal cannot be for another reason.
    manifest.write_text(
        source.replace("slug: fixture-alpine", "slug: fixture-unrendered"), encoding="utf-8"
    )
    assert "fixture-unrendered" in manifest.read_text(encoding="utf-8"), (
        "the slug substitution did not apply, so this would test the rendered control"
    )

    done = run("--project", str(manifest), "--capabilities", CAPABILITIES)
    assert done.returncode == 4, (
        f"an unrendered project exited {done.returncode}, not 4:\n{done.stdout}\n{done.stderr}"
    )
    assert "has not been rendered" in done.stderr
    assert "--render-only" in done.stderr, (
        "the refusal must spell out the command that fixes it, with this invocation's own "
        "arguments rather than as a general instruction"
    )
    assert str(manifest) in done.stderr


def test_a_project_declaring_no_set_generates_the_releases_client(tmp_path: Path) -> None:
    """**GEN-CMD-001.** The boundary ADR 0198 exists to prove.

    `project.second.example.yaml` declares no migration set, so its client is
    generated from the RELEASE's surface and snapshot -- two relations, not
    three, and no `note_embeddings` anywhere. That is the control that a
    project's own set is actually what widens the client, rather than the
    generator reading whatever happens to be in `projects/`.
    """
    out = tmp_path / "release-client"
    done = run(
        "--project",
        PROJECT_WITHOUT_SET,
        "--capabilities",
        CAPABILITIES,
        "--out",
        str(REPO_ROOT / ".generated" / ".client-probe"),
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"

    probe = REPO_ROOT / ".generated" / ".client-probe"
    try:
        ir = json.loads((probe / "generated.json").read_text(encoding="utf-8"))
        relations = [relation["name"] for relation in ir["relations"]]
        assert relations == ["notes", "tasks"], (
            f"a project with no set was generated with {relations}; the release declares two"
        )
        assert ir["project_root"] is None
        assert "note_embeddings" not in (probe / "types.ts").read_text(encoding="utf-8"), (
            "the tenant relation reached a client whose project declares no set"
        )
        assert ir["digests"]["rest_openapi_sha256"] == (
            "85adb686223ea43cf35b92e2d1347dc50c3cd0249ea8d0592340273332fac6c4"
        ), "the release snapshot's fingerprint"
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    assert not out.exists(), "nothing was written to the unused path"


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def _fingerprint(directory: Path) -> dict[str, tuple[int, bytes]]:
    return {
        entry.name: (entry.stat().st_mtime_ns, entry.read_bytes())
        for entry in sorted(directory.iterdir())
        if entry.is_file()
    }


def test_check_agrees_with_the_committed_client_and_writes_nothing() -> None:
    """**GEN-CMD-001.** The drift check, and that it is read-only.

    Asserted over the directory's BYTES AND MTIMES across the call rather than
    by reading the code: `--check` that rewrote a file it considered identical
    would still be a command that writes, and the next `git status` would show
    it after an unrelated regeneration.
    """
    before = _fingerprint(EXAMPLE_CLIENT)
    assert before, "the committed client is empty"

    done = run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check")
    assert done.returncode == 0, (
        f"the committed client is not what its contract generates:\n{done.stdout}\n{done.stderr}"
    )
    assert "is what this contract generates" in done.stdout

    assert _fingerprint(EXAMPLE_CLIENT) == before, "--check modified the client directory"


def test_check_names_the_first_file_that_differs_and_still_writes_nothing() -> None:
    """**GEN-CMD-001.** Drift is exit 5, naming the file.

    The edit is made and reverted here rather than in a copy, because `--check`
    reads the committed path by default and the thing under test is what it
    says about THAT directory. Restored by bytes and compared, never by `git
    checkout --` (the file is tracked, but the habit is what keeps an
    uncommitted neighbour safe).
    """
    target = EXAMPLE_CLIENT / "types.ts"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n// a hand edit\n")
        done = run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check")
        assert done.returncode == 5, f"drift exited {done.returncode}, not 5"
        assert "types.ts differs" in done.stderr
        assert "without --check" in done.stderr, "the message names the way to fix it"
        assert target.read_bytes() == original + b"\n// a hand edit\n", (
            "--check rewrote the file it was reporting on"
        )
    finally:
        target.write_bytes(original)
    assert target.read_bytes() == original, "the client was not restored"

    # And the control: restored, the check passes again.
    assert run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check").returncode == 0


def test_a_missing_generated_file_is_reported_as_missing_not_as_drift() -> None:
    """**GEN-CMD-001.** Two different states, two different messages (ADR 0195).

    A file that was never generated and a file that was edited need different
    actions from the reader, and "differs" for an absent file would send them
    looking for a diff that does not exist.
    """
    target = EXAMPLE_CLIENT / "smoke.ts"
    original = target.read_bytes()
    try:
        target.unlink()
        done = run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check")
        assert done.returncode == 5
        assert "is missing" in done.stderr, f"an absent file was reported as: {done.stderr!r}"
        assert "differs" not in done.stderr
    finally:
        target.write_bytes(original)
    assert run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check").returncode == 0


def test_nothing_the_command_prints_is_a_credential() -> None:
    """**GEN-CMD-001**, D105. There is no token to print, and that is the check.

    The command holds no credential -- it reads four committed artefacts -- so
    this asserts that nothing has been added which would have one, over both
    streams of a successful run and of a refusal.
    """
    import re

    outputs = [
        run("--project", PROJECT, "--capabilities", CAPABILITIES, "--check"),
        run("--project", "no-such-manifest.yaml"),
    ]
    for done in outputs:
        printed = done.stdout + done.stderr
        for pattern in (
            r"eyJ[A-Za-z0-9_-]{10,}\.",
            r"://[^/\s]*:[^/\s]*@",
            r"(?i)\b(password|secret|token)\s*[:=]\s*\S{6,}",
            r"-----BEGIN",
        ):
            assert not re.search(pattern, printed), (
                f"the command printed something matching {pattern}: {printed[:200]!r}"
            )
