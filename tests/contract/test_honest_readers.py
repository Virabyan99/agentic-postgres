"""Unreadable is not absent. ADR 0199, D1060, `OPS-READ-001`.

After a root deploy `.generated/<key>` is root-owned, so `op` cannot traverse
it -- and `bin/migrate.sh`, `bin/db.sh` and `bin/postgres-bootstrap.sh` each
answered *"the project was never deployed here"* about a project deployed
minutes earlier. Measured on the host on 2026-09-10 with beta as the control.

The cause is one line, copied three times:

    [ -f "${document}" ] || die 4 "... the project was never deployed here."

`[ -f ]` answers **false for both** a missing file and one inside a directory
this user cannot traverse. It is not a reader that got the answer wrong; it is a
test that cannot express the question.

**What this module guards is the class, not the three instances** (D600, D918,
D926 each cost a session by fixing the field that failed rather than the
definition). The last test here refuses a `-f` test on a rendered document in
ANY shell under `bin/`, so the fourth copy cannot arrive quietly.

ADR 0195's asymmetry is why the exits differ rather than both being "failure":
a decision may fail closed, a report may not. `migrate.sh render` is a report.
It says which of the two it could not tell.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from agentic_postgres import REPO_ROOT, deployed_output

pytestmark = [pytest.mark.contract, pytest.mark.p0]

RESOLVER = REPO_ROOT / "bin" / "rendered-document.py"

EXIT_UNREADABLE = 3
EXIT_ABSENT = 4


@pytest.fixture
def rendered(tmp_path: Path) -> Path:
    """A checkout-shaped tree: `<root>/.generated/<key>/outputs.json`.

    Shaped like the real thing rather than flattened, because the path the
    reader derives is the thing under test -- a fixture that put the document
    somewhere else would be testing a reader nobody calls.

    Returns the ROOT, which is what `repo_root=` takes.
    """
    directory = tmp_path / ".generated" / "fixture-honest-dev"
    directory.mkdir(parents=True)
    (directory / "outputs.json").write_text(
        json.dumps({"schema_version": 17, "document_kind": "rendered"}), encoding="utf-8"
    )
    return tmp_path


def run_resolver(key: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_as_checkout_owner(), str(REPO_ROOT / ".venv" / "bin" / "python"), str(RESOLVER),
         "--project-key", key],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd or REPO_ROOT,
    )  # fmt: skip


def _as_checkout_owner() -> list[str]:
    """The `sudo -u` prefix that puts a reading in D1060's position, or nothing.

    **D1155, and D1131's shape.** Both refusals in this module are observed by
    reading through a directory the caller cannot traverse -- and root traverses
    everything, so as root there is nothing to observe. The two proofs used to
    carry `skipif(os.geteuid() == 0)`, and the gate runs its static claim proofs
    as root: they skipped on every gate that could have recorded them, and
    `honest_readers` stayed `not_run` for two sessions with both halves written.
    A proof that skips under the identity the gate runs as is a proof the gate
    can never record (D1121, both halves).

    So under root the reading is made as the checkout's OWNER, which is the user
    `op` is after a deploy. Unprivileged, nothing is prefixed and the reading is
    made directly.
    """
    if os.geteuid() != 0:
        return []
    owner = REPO_ROOT.stat()
    if owner.st_uid == 0:
        pytest.skip(
            f"{REPO_ROOT} is root-owned, so there is no unprivileged checkout owner to "
            "make the reading as (D1121/D1155); chown the checkout to the operator first"
        )
    return ["sudo", "-n", "-u", f"#{owner.st_uid}", "-g", f"#{owner.st_gid}"]


#: Read `read_rendered_document` out of process, as the checkout's owner.
#:
#: In process there is no way to drop privilege for one call and put it back, so
#: the reading is made by a subprocess that does the same thing the library does
#: and prints the two values this module asserts on. What it must NOT do is
#: reimplement the reader: it imports and calls it.
_READ_AS_OWNER = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from agentic_postgres import deployed_output

try:
    deployed_output.read_rendered_document(
        sys.argv[3], runtime=False, repo_root=pathlib.Path(sys.argv[2])
    )
except deployed_output.RenderedDocumentUnreadable as error:
    print(json.dumps({"kind": "unreadable", "message": str(error), "owner": error.owner}))
except deployed_output.RenderedDocumentAbsent as error:
    print(json.dumps({"kind": "absent", "message": str(error), "owner": None}))
else:
    print(json.dumps({"kind": "read", "message": "", "owner": None}))
"""


def _unreadable_as_the_checkout_owner(root: Path) -> tuple[str, str | None]:
    """`(message, owner)` from a reading made as the checkout's owner."""
    result = subprocess.run(
        [
            *_as_checkout_owner(),
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            "-c",
            _READ_AS_OWNER,
            str(REPO_ROOT / "src"),
            str(root),
            "fixture-honest-dev",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"the reading as the checkout owner did not run: {result.stderr.strip()[:400]}"
    )
    answer = json.loads(result.stdout)
    assert answer["kind"] == "unreadable", (
        f"reading a 0000 directory as the checkout owner returned {answer['kind']!r}: "
        f"{answer['message']!r}"
    )
    return answer["message"], answer["owner"]


# ---------------------------------------------------------------------------
# The reader itself
# ---------------------------------------------------------------------------


def test_a_readable_document_is_returned_with_its_path(rendered: Path) -> None:
    """The control for both refusals below.

    A reader that raised unconditionally would satisfy every refusal in this
    file, so what a success looks like is asserted first.
    """
    path, document = deployed_output.read_rendered_document(
        "fixture-honest-dev", runtime=False, repo_root=rendered
    )
    assert path.name == "outputs.json"
    assert document["schema_version"] == 17


def test_an_absent_document_is_absent_and_says_never_deployed(tmp_path: Path) -> None:
    with pytest.raises(deployed_output.RenderedDocumentAbsent) as raised:
        deployed_output.read_rendered_document(
            "nothing-here-dev", runtime=False, repo_root=tmp_path
        )
    assert "never deployed here" in str(raised.value)


def test_an_unreadable_document_is_unreadable_and_never_absent(rendered: Path) -> None:
    """The whole defect, in one assertion.

    `chmod 000` on the DIRECTORY rather than on the file, because that is the
    shape the host produces: a root-owned `.generated/<key>` that `op` cannot
    traverse. `stat` on the file inside it raises the same PermissionError the
    traversal did, which is why the owner is resolved by walking upward.

    Under root the reading is made as the checkout's owner rather than skipped
    (D1155); `_as_checkout_owner` carries the reason.
    """
    directory = rendered / ".generated" / "fixture-honest-dev"
    directory.chmod(0o000)
    try:
        if os.geteuid() == 0:
            message, owner = _unreadable_as_the_checkout_owner(rendered)
        else:
            with pytest.raises(deployed_output.RenderedDocumentUnreadable) as raised:
                deployed_output.read_rendered_document(
                    "fixture-honest-dev", runtime=False, repo_root=rendered
                )
            message, owner = str(raised.value), raised.value.owner
    finally:
        directory.chmod(0o755)

    assert directory.stat().st_mode & 0o777 == 0o755, (
        "the fixture directory was not restored, so the next proof inherits a 0000 tree"
    )
    assert (directory / "outputs.json").is_file()

    assert "cannot read" in message
    assert "never deployed" not in message, (
        "an unreadable document was reported with the sentence that means absent, "
        "which is the defect D1060 records"
    )
    assert "chown" in message, "the remedy is not named, so the operator has only the problem"
    assert owner, "the owner could not be determined and was not reported as such"


def test_the_reading_the_root_branch_makes_gives_the_same_answer(rendered: Path) -> None:
    """The out-of-process reading, exercised where it can be exercised.

    D1165's repair replaces a `skipif` with a re-entry as the checkout's owner,
    and that branch runs only under root -- which is the gate and is not this
    workstation. **Everything about it except the `sudo -u` prefix can still be
    run here**, and this runs it: `_unreadable_as_the_checkout_owner` called
    directly, unprivileged, where `_as_checkout_owner` contributes no prefix.

    So what stays unmeasured until the gate is the prefix alone, and that is
    D1131's shape, already proved live on the Session 21 trip. What is measured
    here is the part that is new: that the subprocess imports the reader rather
    than reimplementing it, that its JSON says `unreadable`, and that the answer
    it gives is the SAME answer the in-process reading gives -- which is the
    property that makes the two branches one test rather than two.

    Goes red if: the subprocess loses a path and dies on an import (the first
    version did, with `No module named 'app'`); the reader is reimplemented
    inside it; or the two branches drift apart.
    """
    directory = rendered / ".generated" / "fixture-honest-dev"
    directory.chmod(0o000)
    try:
        out_of_process = _unreadable_as_the_checkout_owner(rendered)
        if os.geteuid() != 0:
            with pytest.raises(deployed_output.RenderedDocumentUnreadable) as raised:
                deployed_output.read_rendered_document(
                    "fixture-honest-dev", runtime=False, repo_root=rendered
                )
            in_process = (str(raised.value), raised.value.owner)
        else:  # pragma: no cover -- root has no in-process reading to compare
            in_process = out_of_process
    finally:
        directory.chmod(0o755)

    assert out_of_process == in_process, (
        f"the reading made out of process says {out_of_process!r} and the one made in "
        f"process says {in_process!r}. The root branch and the unprivileged branch are "
        "supposed to be the same reading made by a different user"
    )

    # The control: with the directory readable, the same subprocess reads the
    # document and the helper's own assertion refuses the answer -- so the
    # helper is not one that reports 'unreadable' whatever it finds.
    with pytest.raises(AssertionError, match="returned 'read'"):
        _unreadable_as_the_checkout_owner(rendered)


def test_the_two_failures_are_different_exceptions() -> None:
    """Not one exception with a flag.

    Six call sites map these to exit codes. A single class carrying a
    discriminator is one `if` away from a caller that forgot to read it, and the
    whole defect is a caller that could not tell two states apart.
    """
    assert not issubclass(
        deployed_output.RenderedDocumentAbsent, deployed_output.RenderedDocumentUnreadable
    )
    assert not issubclass(
        deployed_output.RenderedDocumentUnreadable, deployed_output.RenderedDocumentAbsent
    )


# ---------------------------------------------------------------------------
# The command, end to end
# ---------------------------------------------------------------------------


def test_the_resolver_exits_four_for_a_key_nothing_rendered() -> None:
    result = run_resolver("never-rendered-anywhere-dev")
    assert result.returncode == EXIT_ABSENT, result.stderr
    assert "never deployed here" in result.stderr
    assert result.stdout == "", "a failure printed a path on stdout"


def test_the_resolver_prints_only_the_path_on_success() -> None:
    """A caller does `document="$(...)"`, so stdout is the path and nothing else."""
    result = run_resolver("fixture-alpha-dev")
    if result.returncode != 0:
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")
    assert Path(result.stdout.strip()).name == "outputs.json"
    assert result.stdout.strip().endswith(".generated/fixture-alpha-dev/outputs.json")


def test_the_resolver_exits_three_when_it_cannot_traverse() -> None:
    """The live shape of D1060, on this workstation's own checkout.

    Restored in a `finally`, and the restoration is asserted rather than
    assumed: a test that left `.generated/fixture-alpha-dev` at mode 000 would
    fail every Docker-backed fixture in the suite with an unrelated message.

    Under root the resolver is run as the checkout's owner rather than skipped
    (D1155): `run_resolver` carries the prefix, so this and the control above it
    -- `test_the_resolver_prints_only_the_path_on_success` -- are the same
    reading made by the same user, which is what makes the pair a comparison.
    """
    directory = REPO_ROOT / ".generated" / "fixture-alpha-dev"
    if not (directory / "outputs.json").is_file():
        pytest.skip("no rendered fixture; run ./deploy.sh --render-only")

    before = directory.stat().st_mode
    directory.chmod(0o000)
    try:
        result = run_resolver("fixture-alpha-dev")
    finally:
        directory.chmod(before)

    assert directory.stat().st_mode == before
    assert (directory / "outputs.json").is_file(), "the fixture was not restored"

    assert result.returncode == EXIT_UNREADABLE, result.stderr
    assert "cannot read" in result.stderr
    assert "never deployed" not in result.stderr


# ---------------------------------------------------------------------------
# The class guard (D600, D918, D926)
# ---------------------------------------------------------------------------

#: A shell DERIVING a rendered document's path from a project key.
#:
#: The first version of this guard forbade `[ -f ]` on any variable whose name
#: contained `document`, `outputs` or `rendered`, and it flagged eleven lines in
#: the session gates -- every `[ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not
#: found"`. Those are OPERATOR INPUT validations and they are correct: a path a
#: human typed that is not there should say "not found", and there is no
#: derivation that could have got it wrong.
#:
#: The defect is narrower and this names it: a script that BUILDS the path
#: itself, from `.generated/` or the rendered root plus a key, and then asks
#: `[ -f ]` whether the project was ever deployed. That question cannot be asked
#: with `[ -f ]`, and the three scripts that asked it are the three that were
#: wrong.
#: Order-independent, and that is not a detail. The first version required the
#: root to precede the filename, and
#: `printf '%s/%s/outputs.json' "${RENDERED_ROOT}" "${key}"` -- which is exactly
#: how `bin/postgres-bootstrap.sh` spelled it -- puts them the other way round.
#: This module's own anti-vacuity assertion is what caught that, on the pattern
#: its author had just written.
_DOCUMENT_FILE = re.compile(r"/outputs\.json", re.I)
_DERIVED_ROOT = re.compile(r"\.generated|RENDERED_ROOT", re.I)


#: An ENUMERATION of every rendered document, which is a different thing.
#: `bin/session-01-check.sh` walks `.generated/*/outputs.json` to check every
#: fixture it just rendered; there is no project key, no single document being
#: resolved, and nothing that could answer "was this project ever deployed".
#: The defect is resolving ONE project's document and misreading its absence.
_ENUMERATES = re.compile(r"glob\(|for .* in .*\*/", re.I)


def derives_a_document(line: str) -> bool:
    """A line naming both a derived root and the document's filename.

    An enumeration is not a derivation. Excluding it here rather than in the
    caller so the exclusion has its reason beside it -- an exclusion list that
    lives at the call site is one somebody widens without reading why.
    """
    if _ENUMERATES.search(line):
        return False
    return bool(_DOCUMENT_FILE.search(line) and _DERIVED_ROOT.search(line))


def shell_sources() -> list[Path]:
    return [*sorted((REPO_ROOT / "bin").glob("*.sh")), REPO_ROOT / "deploy.sh"]


def code_of(text: str) -> str:
    """Statements only. These scripts explain the rule in their comments, and a
    scan that matched the sentence forbidding a thing is Session 2 Run 7's
    defect."""
    return "\n".join(line.split("#")[0] for line in text.splitlines())


def test_no_shell_derives_a_rendered_documents_path_for_itself() -> None:
    """The guard on the class rather than on the three instances.

    Three scripts carried one wrong line. Repairing three scripts leaves the
    fourth copy free to arrive, and it would arrive the way the first three did
    -- by somebody reasonably building `${ROOT_DIR}/.generated/${key}/
    outputs.json` and asking `[ -f ]` whether the project was ever deployed.

    `bin/rendered-document.py` is the one place that path is spelled, so a
    second spelling in a shell is either a second answer to where the document
    is or a second answer to what its absence means -- and this defect was both.

    Anti-vacuity: the pattern is asserted to MATCH the line it exists to forbid,
    so a regex that had stopped matching anything could not pass this by
    scanning clean files.
    """
    assert derives_a_document('    document="${ROOT_DIR}/.generated/${key}/outputs.json"'), (
        "the reader no longer matches the line it exists to forbid"
    )
    assert derives_a_document('    printf \'%s/%s/outputs.json\' "${RENDERED_ROOT}" "${key}"'), (
        "the reader misses the rendered-root spelling, where the filename comes FIRST"
    )
    assert not derives_a_document('    [ -f "${PROJECT_A_OUTPUTS}" ] || die 2 "not found"'), (
        "the reader flags an operator-supplied path, which is an input validation and not "
        "a derivation -- the over-broad first version flagged eleven of these in the gates"
    )

    offenders: list[str] = []
    for path in shell_sources():
        if not path.is_file():
            continue
        for number, line in enumerate(code_of(path.read_text(encoding="utf-8")).splitlines(), 1):
            if derives_a_document(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")

    assert not offenders, (
        "these shells derive a rendered document's path for themselves, which is where "
        "`[ -f ]` then answers false both for a missing file and for one this user cannot "
        "traverse to (D1060):\n  "
        + "\n  ".join(offenders)
        + "\nUse bin/rendered-document.py: it exits 3 for unreadable and 4 for absent."
    )


def test_the_three_repaired_shells_call_the_resolver() -> None:
    """The positive half. Without it, the guard above passes for a script that
    deleted its check entirely and reads an unresolved path."""
    for name in ("migrate.sh", "db.sh", "postgres-bootstrap.sh"):
        source = code_of((REPO_ROOT / "bin" / name).read_text(encoding="utf-8"))
        assert "bin/rendered-document.py" in source, f"{name} resolves its document some other way"
        assert 'exit "${status}"' in source, (
            f"{name} calls the resolver and does not propagate its exit code, so an "
            "unreadable document would read as an empty path"
        )


def test_upgrade_already_distinguished_the_two_and_still_does() -> None:
    """`bin/upgrade.py` is the one reader that got this right before ADR 0199.

    Asserted rather than rewritten. The plan listed six readers needing the
    change; measured, this one already had it -- distinct exit codes AND
    distinct messages -- and rewriting a correct reader to use a new helper
    would be a change with no defect behind it. What is worth having is a test
    that says so, so the next person does not have to measure it again.
    """
    source = (REPO_ROOT / "bin" / "upgrade.py").read_text(encoding="utf-8")
    body = source.split("def read_document(", 1)[1].split("\ndef ", 1)[0]
    assert "except FileNotFoundError" in body
    assert "except PermissionError" in body
    assert body.index("except FileNotFoundError") != body.index("except PermissionError")
    assert "EXIT_MISSING" in body and "EXIT_PREREQUISITE" in body


def test_the_doctor_reads_the_deployed_document_and_does_not_claim_absence() -> None:
    """The doctor's reader is a DIFFERENT artefact, and it is already honest.

    It reads `/etc/agentic-postgres/projects/<key>/outputs.json` -- the deployed
    document -- not a rendered one. Both failures exit `EXIT_STATE`, which is
    coarser than the resolver's 3-and-4; what matters for ADR 0195 is that the
    MESSAGES differ, and that the unreadable one does not assert absence.
    """
    source = (REPO_ROOT / "bin" / "doctor.py").read_text(encoding="utf-8")
    body = source.split("def load_document(", 1)[1].split("\ndef ", 1)[0]
    assert "deployed_path" in body, "the doctor now reads a rendered document; retest this"
    assert "has not been deployed on this host" in body
    assert "could not be read" in body

    absent_at = body.index("has not been deployed on this host")
    unreadable_at = body.index("could not be read")
    assert absent_at != unreadable_at
    between = body[min(absent_at, unreadable_at) : max(absent_at, unreadable_at)]
    assert "except OSError" in between or "except FileNotFoundError" in between


def test_project_retire_reads_no_rendered_document() -> None:
    """Recorded so the requirement's text can be true.

    `OPS-READ-001` as drafted names six readers. This one removes a rendered
    directory and never reads a document out of it, so there is nothing here to
    make honest -- and a requirement claiming otherwise would be a claim no
    proof could satisfy.
    """
    source = (REPO_ROOT / "bin" / "project-retire.py").read_text(encoding="utf-8")
    assert "RENDERED_ROOT" in source
    assert "rendered_path(" not in source
    assert 'read_text(encoding="utf-8")' not in source.split("rendered_root=", 1)[1][:400]


# ---------------------------------------------------------------------------
# OPS-READ-002 -- `unobserved` has a writer (ADR 0199, D1048)
# ---------------------------------------------------------------------------

import importlib.util  # noqa: E402


@pytest.fixture(scope="module")
def deploy_module():
    """`bin/deploy-project.py`, imported rather than shelled out to.

    The observers are pure functions of a probe's output once the probe has
    run, and that is the half under test here: which WORD a given answer
    becomes. Whether curl reaches the route is the trip's.
    """
    specification = importlib.util.spec_from_file_location(
        "apg_deploy_project", REPO_ROOT / "bin" / "deploy-project.py"
    )
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "status,expected",
    [
        ("200", "ready"),
        ("500", "unavailable"),
        ("404", "unavailable"),
        ("401", "unavailable"),
        ("000", "unobserved"),
        ("", "unobserved"),
    ],
)
def test_a_status_that_was_obtained_is_unavailable_and_one_that_was_not_is_unobserved(
    deploy_module, status: str, expected: str
) -> None:
    """The rule, as a table. ADR 0199's division, in one function.

    `000` is what curl writes for `%{http_code}` when it never received an HTTP
    response -- DNS, TLS, refused, or `--max-time` exceeded. An empty string is
    what arrives if the process could not be run at all. Both mean the deploy
    did not obtain an answer; every other value means it did.

    The three `unavailable` arms are the ones that keep this honest. A change
    that made every non-ready answer `unobserved` would satisfy the two arms
    below and would be the opposite defect: a deploy claiming it had not looked
    when it had.
    """
    assert deploy_module.observed(status, ready_when="200") == expected


def test_the_ready_status_is_the_callers_and_not_a_constant(deploy_module) -> None:
    """`ready_when` is a parameter because the routes disagree about it.

    `health` is ready at 200; `app`, `storage` and `docs` are ready at 401,
    because their healthy answer is a REFUSAL -- asserting 200 on them would be
    asserting the boundary is open. A helper with 200 baked in would have made
    three routes permanently unavailable.
    """
    assert deploy_module.observed("401", ready_when="401") == "ready"
    assert deploy_module.observed("200", ready_when="401") == "unavailable"
    assert deploy_module.observed("000", ready_when="401") == "unobserved"


def test_every_route_observer_records_a_word_the_schema_admits(deploy_module) -> None:
    """Anti-vacuity on the table above: the words are the schema's.

    A helper returning `"unobserved "` with a trailing space, or `"not_
    observed"`, would satisfy every assertion above and be refused by
    `published_route` at the moment a deploy tried to record it -- on a host,
    after the work was done.
    """
    produced = {
        deploy_module.observed(status, ready_when="200") for status in ("200", "500", "000", "")
    }
    assert produced == set(deployed_output.ROUTE_STATUSES)


def test_the_docs_observer_records_unobserved_when_the_connection_never_became_one(
    deploy_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clearest instance in the deploy: `observe_docs`'s exception path.

    D1047's staging certificate and D326's first-deploy router race both arrive
    here -- a connection that never became an HTTP response. Until version 17
    both recorded the same word as a route observed serving a 200 to anyone who
    asked, which is the state `unavailable` is for.
    """
    calls: list[str] = []

    class Failing:
        @staticmethod
        def check(url: str) -> int:
            raise OSError("certificate verify failed: self-signed certificate")

    monkeypatch.setattr(deploy_module, "_load_command", lambda *a, **k: Failing)
    monkeypatch.setattr(deploy_module, "_report_docs_failure", lambda url, error: calls.append(url))

    assert deploy_module.observe_docs("https://example.test/docs/rest") == "unobserved"
    assert calls, "the failure was recorded as unobserved and never reported"


def test_published_address_refuses_an_unobserved_route_with_the_remedy() -> None:
    """The reader ADR 0199 names, and the sentence that makes it useful.

    `unobserved` and `unavailable` both withhold the URL, so a reader that
    folded them would tell an operator to check which session their project was
    deployed through -- when the answer is "redeploy so the route is observed".
    """
    import importlib.util as _util

    specification = _util.spec_from_file_location(
        "apg_api_contract_reader", REPO_ROOT / "bin" / "api-contract.py"
    )
    module = _util.module_from_spec(specification)
    specification.loader.exec_module(module)

    unobserved = {"routes": {"rest": {"status": "unobserved", "url": None}}}
    with pytest.raises(module.ContractError) as raised:
        module.published_address(unobserved)
    assert "unobserved" in str(raised.value)
    assert "Redeploy" in str(raised.value)

    # The control: `unavailable` keeps its own, different message.
    unavailable = {"routes": {"rest": {"status": "unavailable", "url": None}}}
    with pytest.raises(module.ContractError) as raised:
        module.published_address(unavailable)
    assert "Redeploy" not in str(raised.value), (
        "an observed-and-not-serving route was given the unobserved remedy, so the two "
        "states are indistinguishable to the operator reading the message"
    )


def test_publish_and_load_rendered_name_the_owner_and_the_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1151: the two readers that crashed on the state D1154 recorded.

    The Session 21 sweep left `.generated/alpha-dev` root-owned, and
    `rendering.publish` and `evidence.load_rendered` both died with
    `PermissionError` -- `[Errno 13] Permission denied` about a path whose
    parent the operator owns, which reads as a broken disk rather than as a
    permission a privileged render took. This is ADR 0195's rule applied to the
    two of them: the third outcome is reported, and a report that cannot be
    acted on is half a report, so the owner and the `chown` are named.

    `publish`'s half is in `test_render_atomicity.py`, where the renderer's
    proofs live; this is `load_rendered`'s, and the assertion that the two say
    the same three things is what keeps them one class rather than two repairs.

    Under root the reading is made as the checkout's owner (D1155,
    `_as_checkout_owner`): root traverses a 0000 directory and there would be
    nothing to observe.
    """
    generated = tmp_path / ".generated"
    directory = generated / "fixture-shut-dev"
    directory.mkdir(parents=True)
    (directory / "outputs.json").write_text(
        json.dumps({"schema_version": 17, "document_kind": "rendered"}), encoding="utf-8"
    )
    directory.chmod(0o000)
    try:
        result = subprocess.run(
            [
                *_as_checkout_owner(),
                str(REPO_ROOT / ".venv" / "bin" / "python"),
                "-c",
                _LOAD_RENDERED_AS_OWNER,
                str(REPO_ROOT / "src"),
                str(REPO_ROOT / "services" / "auth-api"),
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        directory.chmod(0o755)

    assert directory.stat().st_mode & 0o777 == 0o755, "the fixture directory was not restored"
    assert result.returncode == 0, (
        f"the reading as the checkout owner did not run: {result.stderr.strip()[:400]}"
    )
    answer = json.loads(result.stdout)
    assert answer["kind"] == "evidence_error", (
        f"an unreadable rendered directory came back as {answer['kind']!r}: "
        f"{answer['message']!r}. A bare PermissionError is what D1151 records"
    )

    message = answer["message"]
    assert "cannot read" in message
    assert "owned by" in message and "this user is" in message, message
    assert "chown" in message, "the remedy is not named, so the operator has only the problem"
    assert "Errno 13" not in message, (
        "the operating system's own message was relayed rather than read"
    )


#: `evidence.load_rendered` against a checkout-shaped root, out of process.
#:
#: Out of process for the same reason the reader above is: privilege cannot be
#: dropped for one call and put back. It imports the library rather than
#: reimplementing it -- a fixture that shared the code's belief is D673's class.
_LOAD_RENDERED_AS_OWNER = """
import json, pathlib, sys
# Both roots, because `pytest.ini` puts both on the path and the import chain
# behind `evidence` reaches the service package. A subprocess with only `src`
# dies with `No module named 'app'`, which is a path problem wearing the costume
# of the permission problem under test.
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from agentic_postgres import evidence

evidence.REPO_ROOT = pathlib.Path(sys.argv[3])
try:
    evidence.load_rendered()
except evidence.EvidenceError as error:
    print(json.dumps({"kind": "evidence_error", "message": str(error)}))
except PermissionError as error:
    print(json.dumps({"kind": "permission_error", "message": str(error)}))
else:
    print(json.dumps({"kind": "read", "message": ""}))
"""
