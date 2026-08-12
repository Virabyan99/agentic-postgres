"""`bin/api-contract.sh`, and the property ADR 0050 asks for structurally.

The one that matters is that **the check cannot approve its own subject**. It is
asserted three ways, because "never writes" is the kind of claim a test passes
by not exercising the path that would: the command's own source is scanned for a
writer, the check is run against a repository whose snapshot is deliberately
wrong, and the file is confirmed unchanged afterwards.

`contracts/postgrest-openapi.canonical.json` was captured in Run 9 from the
deployed release at `alpha-db`, reviewed, and committed. Before that it did not
exist, and two tests here were written around its absence; both have been
replaced by stricter ones under ADR 0050 rather than deleted, and each says so
in its own docstring. The tests that need a *wrong* snapshot still build one in
a temporary directory and point the module at it, because the committed file is
never a test's to edit.

What the review found, recorded here because it is the reason the snapshot is
trusted: the captured document is **identical** to the normalized fixture, which
was re-captured independently from `.generated/fixture-alpha-dev/migrations/` on
a throwaway cluster. Two different clusters, one built by the deploy and one by
the rig, produced the same document from the same nine migrations.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, api_surface, openapi_normalize

pytestmark = [pytest.mark.contract, pytest.mark.p0]

COMMAND = REPO_ROOT / "bin" / "api-contract.sh"
MODULE = REPO_ROOT / "bin" / "api-contract.py"
CAPTURED = REPO_ROOT / "tests" / "fixtures" / "postgrest-openapi.captured.json"

CAPTURED_HOST = "alpha.example.test:443"
CAPTURED_BASE_PATH = "/api/rest"


@pytest.fixture
def api_contract():
    """The command module, imported rather than shelled out to.

    Imported so the comparison functions can be driven directly. The shell
    wrapper is exercised separately, because what it contributes -- argument
    refusal and exit codes -- is not visible from inside the module.
    """
    sys.path.insert(0, str(REPO_ROOT / "bin"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("apg_api_contract", MODULE)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(REPO_ROOT / "bin"))


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(COMMAND), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
    )


def approved_snapshot() -> dict[str, Any]:
    """The captured document, normalized -- what Run 9 will commit."""
    return openapi_normalize.normalize(
        openapi_normalize.load_document(CAPTURED.read_bytes()),
        expected_host=CAPTURED_HOST,
        expected_base_path=CAPTURED_BASE_PATH,
    )


# ---------------------------------------------------------------------------
# The state the repository is actually in
# ---------------------------------------------------------------------------


def test_the_approved_snapshot_exists_and_check_compares_it() -> None:
    """The replacement its predecessor asked for, under ADR 0050.

    Until Run 9 this asserted the snapshot was *absent* and `--check` exited 5
    naming the run that would produce one, because a green `--check` with
    nothing to compare is a gate measuring nothing. Run 9 captured one from the
    deployed release at `alpha-db`, so the assertion inverts rather than
    disappears: the file exists, it is the generated artifact, and `--check`
    reaches a real comparison and passes it.

    Goes red if the snapshot is deleted, hand-edited into non-canonical form, or
    stops matching the reviewed surface -- each of which is the state the
    predecessor existed to keep out.
    """
    snapshot = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
    assert snapshot.exists(), "the approved snapshot is missing; re-capture it, do not skip"

    approved = json.loads(snapshot.read_bytes())
    assert approved["host"] == openapi_normalize.SENTINEL_HOST
    assert approved["basePath"] == openapi_normalize.SENTINEL_BASE_PATH
    assert snapshot.read_bytes() == openapi_normalize.canonical_bytes(approved)

    result = run("--check")
    assert result.returncode == 0, result.stderr
    # The count is the comparison's own evidence that it had something to do.
    assert "4 objects" in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# ADR 0050 -- the gate cannot approve its own subject
# ---------------------------------------------------------------------------


#: Each is a regex, not a substring, because the scan now covers a call graph
#: rather than one function body and the looser spelling collides. `open(`
#: matched `urlopen(` inside `fetch_live`, which reads the live document and
#: writes nothing -- a false positive that would have been "fixed" by dropping
#: the token, quietly removing the only check on the plainest writer there is.
WRITERS = (
    r"\bwrite_text\s*\(",
    r"\bwrite_bytes\s*\(",
    r"\bos\.replace\s*\(",
    r"\bmkstemp\s*\(",
    r"(?<![\w.])open\s*\(",
)


def _reachable_from(source: str, entry: str) -> dict[str, str]:
    """Every module-level function `entry` can reach, mapped to its source.

    Text slicing cannot answer this: it sees one function body and stops at the
    next `def`. A repair path one call away is invisible to it, which was
    measured rather than supposed -- a helper that writes the snapshot and is
    called from `command_check`'s first line left the old assertion green
    (D191).
    """
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    seen: dict[str, str] = {}
    pending = [entry]
    while pending:
        name = pending.pop()
        node = functions.get(name)
        if node is None or name in seen:
            continue
        seen[name] = ast.get_source_segment(source, node) or ""
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            func = call.func
            called = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if called in functions and called not in seen:
                pending.append(called)
    return seen


def test_the_check_path_contains_no_writer() -> None:
    """Structural, not behavioural: there is no code to reach.

    `command_update` is the only writer, and it writes to a stream rather than a
    path. Goes red if `--check` ever grows a repair mode, which is the change
    that would turn the gate into something that can approve its own subject.

    The whole reachable call graph is scanned, not `command_check`'s own body.
    The body-only version passed a reachable `SNAPSHOT_PATH.write_bytes(...)`
    sitting one call away, and the behavioural half below did not catch it
    either, so the property had a hole exactly the width of one function call
    (D191).
    """
    source = MODULE.read_text(encoding="utf-8")
    reachable = _reachable_from(source, "command_check")

    # The control: a graph walk that found nothing would pass this test forever.
    assert "command_check" in reachable
    assert {"load_snapshot", "fetch_live"} <= set(reachable), (
        f"the walk reached only {sorted(reachable)}; it is not following calls"
    )
    assert "command_update" not in reachable, "the check path reaches the capture path"

    for name, body in sorted(reachable.items()):
        stripped = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )
        for writer in WRITERS:
            found = re.search(writer, stripped)
            assert not found, f"command_check reaches a writer: {name} uses {found.group(0)!r}"


def test_update_names_no_output_path() -> None:
    """The candidate is streamed, so the redirect is the caller's.

    An `--output` option would put the file's ownership in the privileged
    process, which is precisely what ADR 0050's "it writes no source file" is
    for: the reviewer has to be able to edit and commit what came out.
    """
    help_text = run("--help").stdout
    assert "--output" not in help_text
    assert "standard output" in help_text
    source = MODULE.read_text(encoding="utf-8")
    assert '"--output"' not in source


def test_a_failing_check_leaves_both_contract_files_untouched(tmp_path: Path) -> None:
    """The behavioural half: a check that repaired would leave no trace of failing.

    Until Run 9 the failure came for free -- there was no snapshot, so every
    `--check` exited non-zero. Now that one is committed the check passes, and a
    test whose failure is supplied by an absent file would be asserting nothing
    about the writer. The failure is induced instead, by naming a deployed
    document that does not exist, and the two committed contract files are
    compared byte-for-byte across it.

    Goes red if `--check` ever gains a repair path, and -- unlike its
    predecessor -- it would still go red with the snapshot present, which is the
    only state this repository will ever be in again.

    **The failure has to land inside `command_check`.** Naming an absent
    deployed document exits 2 and pointing at an unreachable one with no token
    exits 3, both from the shell wrapper before Python runs -- so either would
    assert nothing about a writer. This supplies a token so the wrapper's
    prerequisites pass, and an address nothing answers on, which fails at
    `fetch_live` after `load_snapshot` and the surface comparison have already
    run. That ordering is the point: a repair path at the top of the function
    would have executed by then (D191).
    """
    outputs = tmp_path / "outputs.json"
    outputs.write_text(
        json.dumps(
            {"routes": {"rest": {"url": "https://127.0.0.1:9/api/rest", "status": "ready"}}}
        ),
        encoding="utf-8",
    )

    surface_before = api_surface.CONTRACT_PATH.read_bytes()
    snapshot_path = REPO_ROOT / "contracts" / "postgrest-openapi.canonical.json"
    snapshot_before = snapshot_path.read_bytes()

    result = run(
        "--check",
        "--project-outputs",
        str(outputs),
        env={"APG_DOCS_TOKEN": "not-a-real-token"},
    )
    assert result.returncode != 0, "the check was supposed to fail; it did not"
    # The control on *where* it failed. Exit 2 or 3 from the wrapper would mean
    # command_check never ran and this test measured nothing.
    assert "cannot reach the REST service" in result.stderr, result.stderr

    assert api_surface.CONTRACT_PATH.read_bytes() == surface_before
    assert snapshot_path.read_bytes() == snapshot_before


# ---------------------------------------------------------------------------
# The comparison -- ADR 0060's object level
# ---------------------------------------------------------------------------


def test_the_captured_surface_agrees_with_the_reviewed_contract(api_contract) -> None:
    """The control for every disagreement test below.

    The captured document was produced from a schema shaped like the reviewed
    contract, so the comparison must find nothing. If this goes red, every
    "disagreement is reported" test below could be passing on a mismatch that
    was already there.
    """
    surface = api_surface.load_surface()
    assert api_contract.compare_snapshot_to_surface(approved_snapshot(), surface) == []


def test_an_object_in_the_document_and_not_the_contract_is_reported(api_contract) -> None:
    """ADR 0050: an object reaching the published document without a reviewed
    entry is the case the contract exists for."""
    snapshot = approved_snapshot()
    snapshot["paths"]["/rpc/quietly_added"] = {"post": {}}
    problems = api_contract.compare_snapshot_to_surface(snapshot, api_surface.load_surface())
    assert any("rpc/quietly_added" in problem for problem in problems)


def test_an_object_in_the_contract_and_not_the_document_is_reported(api_contract) -> None:
    snapshot = approved_snapshot()
    del snapshot["paths"]["/notes"]
    problems = api_contract.compare_snapshot_to_surface(snapshot, api_surface.load_surface())
    assert any("'notes'" in problem for problem in problems)


def test_the_methods_are_not_compared(api_contract) -> None:
    """ADR 0060, asserted rather than left implicit in an absence.

    The captured document advertises `delete`, `patch` and `post` on `/notes`
    while the reviewed contract names only `GET` and `HEAD`, and all three
    writes return 403 against a SELECT-only grant. A comparator that compared
    methods would fail here forever, and the repair somebody would reach for is
    widening the contract -- which converts the reviewed read-only surface into
    a permissive one.

    Goes red if method comparison is ever added, which is the point.
    """
    snapshot = approved_snapshot()
    assert set(snapshot["paths"]["/notes"]) == {"delete", "get", "patch", "post"}
    assert api_surface.load_surface()["relations"]["notes"]["methods"] == ["GET", "HEAD"]
    assert api_contract.compare_snapshot_to_surface(snapshot, api_surface.load_surface()) == []


# ---------------------------------------------------------------------------
# The published address, derived rather than accepted
# ---------------------------------------------------------------------------


def test_the_published_address_is_derived_from_the_deployed_route(api_contract) -> None:
    """`:443` is measured, not assumed.

    Given `openapi-server-proxy-uri` of `https://alpha.example.test/api/rest`,
    the locked PostgREST published `host: "alpha.example.test:443"`. A derivation
    that dropped the port would refuse every correct capture, and one that added
    it twice would refuse them all differently.
    """
    deployed = {
        "routes": {"rest": {"status": "ready", "url": "https://alpha.example.test/api/rest"}}
    }
    assert api_contract.published_address(deployed) == (CAPTURED_HOST, CAPTURED_BASE_PATH)


def test_an_explicit_port_is_kept(api_contract) -> None:
    deployed = {"routes": {"rest": {"status": "ready", "url": "https://alpha.example.test:8443/x"}}}
    assert api_contract.published_address(deployed)[0] == "alpha.example.test:8443"


def test_a_project_with_no_rest_route_is_refused(api_contract) -> None:
    """Every project deployed before session 5 is in this state, and a capture
    against one would otherwise fetch nothing and normalize it successfully."""
    deployed = {"routes": {"rest": {"status": "unavailable", "url": None}}}
    with pytest.raises(api_contract.ContractError) as raised:
        api_contract.published_address(deployed)
    assert raised.value.code == 2


# ---------------------------------------------------------------------------
# The snapshot is a generated artifact
# ---------------------------------------------------------------------------


def test_a_hand_edited_snapshot_is_refused(api_contract, tmp_path: Path, monkeypatch) -> None:
    """Re-serializing the parse and comparing it to the bytes is what catches it.

    A snapshot somebody reformatted, resorted or edited one line of no longer
    matches what the generator would produce -- which is the state in which the
    committed file has stopped being the generated artifact ADR 0050 says it is.
    """
    snapshot = tmp_path / "canonical.json"
    approved = approved_snapshot()
    snapshot.write_bytes(openapi_normalize.canonical_bytes(approved))
    monkeypatch.setattr(api_contract, "SNAPSHOT_PATH", snapshot)
    assert api_contract.load_snapshot() == approved  # the control

    snapshot.write_text(json.dumps(approved, indent=4) + "\n", encoding="utf-8")
    with pytest.raises(api_contract.ContractError) as raised:
        api_contract.load_snapshot()
    assert raised.value.code == 5
    assert "canonical form" in str(raised.value)


def test_a_snapshot_carrying_a_real_host_is_refused(
    api_contract, tmp_path: Path, monkeypatch
) -> None:
    """One project's document committed as both projects'."""
    snapshot = tmp_path / "canonical.json"
    approved = approved_snapshot()
    approved["host"] = CAPTURED_HOST
    snapshot.write_bytes(openapi_normalize.canonical_bytes(approved))
    monkeypatch.setattr(api_contract, "SNAPSHOT_PATH", snapshot)
    with pytest.raises(api_contract.ContractError) as raised:
        api_contract.load_snapshot()
    assert raised.value.code == 5
    assert "sentinel" in str(raised.value)


# ---------------------------------------------------------------------------
# No credential in argv (D105)
# ---------------------------------------------------------------------------


def test_the_token_is_read_from_the_environment_and_not_an_argument() -> None:
    """argv is readable by every user on the host through `ps`."""
    help_text = run("--help").stdout
    assert "APG_DOCS_TOKEN" in help_text
    assert "--token" not in help_text
    source = MODULE.read_text(encoding="utf-8")
    assert 'add_argument("--token' not in source


def test_a_capture_without_a_token_refuses_before_reaching_the_network(tmp_path: Path) -> None:
    """Exit 3, a missing prerequisite -- not a network error somewhere later.

    The outputs document names a host that does not resolve, so if the refusal
    were not first this would fail with a connection error instead.
    """
    outputs = tmp_path / "outputs.json"
    outputs.write_text(
        json.dumps(
            {"routes": {"rest": {"status": "ready", "url": "https://nothing.invalid/api/rest"}}}
        ),
        encoding="utf-8",
    )
    result = run("--update", "--project-outputs", str(outputs), env={"APG_DOCS_TOKEN": ""})
    assert result.returncode == 3, result.stderr
    assert "APG_DOCS_TOKEN" in result.stderr


def test_the_command_does_not_echo_a_planted_token() -> None:
    planted = "APG_CANARY_TOKEN_7Yh2Qx"
    result = run("--check", env={"APG_DOCS_TOKEN": planted})
    assert planted not in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Argument refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), 2),
        (("--bogus",), 2),
        (("--check", "--update"), 2),
        (("--update",), 2),
        (("--project-outputs",), 2),
        (("--check", "--project-outputs", "/does/not/exist.json"), 2),
    ],
)
def test_invalid_input_exits_two(args: tuple[str, ...], expected: int) -> None:
    assert run(*args).returncode == expected


def test_help_works_from_another_directory(tmp_path: Path) -> None:
    assert run("--help", cwd=tmp_path).returncode == 0
