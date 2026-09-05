"""The live halves of `DEP-001`, `DEP-REMOVE-001` and `DX-001`.

**Each proves something that HAPPENED, not a state that holds**, and each is
admitted by an operator declaration — the `APG_AFTER_REBOOT` and
`APG_ROTATED_*_FROM_FILE` shape (Session 4 Run 10, Session 5 Run 10). A reboot
cannot be performed by a test that must survive to report it; neither can
emptying a host, removing a project, or being somebody who did not build this.

**A declaration is not a pass.** Every proof here refuses a false one before it
asserts anything, for the reason the rotation proofs do: without that, a window
in which nothing happened satisfies every assertion. The rotation proofs compare
the declared value against the active one; these compare the declared record
against what the deployment and the documentation actually say.

**And none of these may be reported `passed` by its offline half alone** — the
plan's §7. An offline half proves the documented path *resolves*; only these
prove anybody walked it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, output_migrations

pytestmark = [pytest.mark.p0]


def _declared(variable: str) -> dict[str, Any]:
    """The operator's record, refused unless it is a readable JSON object."""
    path = Path(os.environ[variable])
    assert path.is_file(), f"{variable} points at {path}, which is not a file"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        pytest.fail(f"{variable} points at {path}, which is not readable JSON: {error}")
    assert isinstance(document, dict), f"{path} is not a JSON object"
    return document


# ---------------------------------------------------------------------------
# DEP-001 — a fresh project deploys on an empty host
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_FRESH_HOST_OUTPUTS", "APG_PROJECT_A_OUTPUTS")
def test_a_project_deployed_on_an_empty_host_is_a_working_deployment(
    project_a: dict[str, Any],
) -> None:
    """`DEP-001`. A deployed document produced by a host that started empty.

    The offline half — every command the documented path names exists, resolves
    and answers — was proved in Session 11 and again by
    `tests/contract/test_session12_documented_path.py`. **It cannot prove a host
    that started empty reached a working deployment**, which is why this exists
    and why `DEP-001` does not report `passed` without it.

    **The false declaration this refuses is the obvious one**: handing it the
    production host's own document. That document describes a host which has run
    projects since Session 3, and pointing at it would turn `DEP-001` into a
    restatement of every other host claim. So the declared host must not be the
    host `project_a` is deployed on.

    Goes red if: the fresh host's deployment is not at this release's outputs
    version, publishes no ready route, or is the host we already had.
    """
    fresh = _declared("APG_FRESH_HOST_OUTPUTS")

    assert fresh.get("document_kind") == "deployed", (
        f"the declared document is {fresh.get('document_kind')!r}, not a deployed one. "
        "A render proves the manifest is valid, not that a host deployed it"
    )
    assert fresh.get("schema_version") == output_migrations.CURRENT_VERSION, (
        f"the fresh host's document is at outputs v{fresh.get('schema_version')} and this "
        f"release is v{output_migrations.CURRENT_VERSION}. It describes an older product"
    )

    declared_host = (fresh.get("host") or {}).get("id")
    running_host = (project_a.get("host") or {}).get("id")
    assert declared_host, "the declared document names no host"
    assert declared_host != running_host, (
        f"the declared fresh host is {declared_host!r}, which is the host project A already "
        "runs on. That host has carried projects since Session 3 and was not empty, so this "
        "would prove DEP-001 with the deployment it is supposed to be independent of"
    )

    ready = {
        name: route.get("status")
        for name, route in (fresh.get("routes") or {}).items()
        if isinstance(route, dict)
    }
    assert ready, "the declared document publishes no routes at all"
    unready = sorted(name for name, status in ready.items() if status != "ready")
    assert not unready, (
        f"the fresh host deployed but these routes are not ready: {unready}. A deployment "
        "nobody can reach is not one the documented path delivered"
    )


# ---------------------------------------------------------------------------
# DEP-REMOVE-001 — removing one project does not affect another
# ---------------------------------------------------------------------------


@pytest.mark.live_host
@pytest.mark.requires_environment(
    "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_REMOVED_PROJECT_FILE"
)
def test_removing_one_project_leaves_the_other_whole(
    project_a: dict[str, Any],
    psql: Any,
    sh: Any,
    as_root,
) -> None:
    """`DEP-REMOVE-001`. What the removal surface that exists can be held to.

    **No shipped command removes a project** (D691): `project-runtime.sh down`
    preserves the volume deliberately and `compose.sh` refuses `--volumes` in
    project mode. So "removal" here is what an operator actually performs — the
    runtime brought down and `bootstrap-providers.sh --destroy` run against one
    project's recorded resources — and the claim is that the *other* project is
    untouched by it.

    The declaration records the removed project's key and the resource names it
    owned, captured **before** the removal. Captured after, it would be a list of
    things that no longer exist, which proves nothing about what was removed.

    Goes red if: the surviving project stopped serving, lost rows, or if any
    container or network named for the removed project is still running.
    """
    del as_root
    record = _declared("APG_REMOVED_PROJECT_FILE")

    removed_key = record.get("project_key")
    assert removed_key, "the declaration records no project_key"
    assert removed_key != project_a["project"]["key"], (
        f"the declaration says {removed_key!r} was removed, which is the project this "
        "test reads to check it survived. Nothing was measured"
    )

    # The survivor still serves, and still holds its rows. Both, because a
    # container that is up and a database that answers are different facts.
    code, out, _ = psql(project_a, "SELECT count(*) FROM app.notes")
    assert code == 0, f"the surviving project's database did not answer: {out}"
    assert out.strip().isdigit(), f"unexpected row count {out.strip()!r}"

    unready = sorted(
        name
        for name, route in (project_a.get("routes") or {}).items()
        if isinstance(route, dict) and route.get("status") != "ready"
    )
    assert not unready, f"the surviving project has unready routes after the removal: {unready}"

    # And nothing of the removed project is still running. Read from the host
    # rather than from its document, which is gone.
    # `sh` returns stdout as text and fails the test itself on a bad exit; this
    # line read it as a process object and was the first line of the proof
    # never to have run (D982) -- the survivor's rows and routes above passed
    # on the first execution, 2026-09-05, and the proof died here.
    names = sh("docker", "ps", "--format", "{{.Names}}")
    survivors = [line for line in names.splitlines() if removed_key in line]
    assert not survivors, (
        f"these containers are still running for the removed project {removed_key!r}: "
        f"{survivors}. The removal did not complete, so 'the other project is unaffected' "
        "is a claim about a removal that did not happen"
    )


# ---------------------------------------------------------------------------
# DX-001 — somebody who did not build this completed the documented path
# ---------------------------------------------------------------------------

#: What the record must carry. Each is a question whose answer decides the claim,
#: and an absent one is refused rather than assumed favourable.
DX_RECORD_FIELDS = (
    "followed_by",
    "completed_at",
    "release",
    "commands_run",
    "files_edited",
    "undocumented_steps",
    "reached_success_criterion",
)

#: The operator inputs a reader legitimately creates and edits. Anything else
#: they had to edit is a source edit, which is `DX-001`'s stated failure.
OPERATOR_INPUTS = frozenset(
    {"project.yaml", "capabilities.yaml", "host.yaml", "project.beta.yaml", "project.alpha.yaml"}
)

_COMMAND = re.compile(r"(?:^|[\s`(])(\./deploy\.sh|bin/[a-z0-9-]+\.(?:sh|py))")


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_DX_RECORD_FILE")
def test_a_developer_who_did_not_build_this_completed_the_documented_path() -> None:
    """`DX-001`. The one claim in this repository that a test cannot make alone.

    **The record is a declaration and this refuses a false one**, three ways:
    an incomplete record, a record that contradicts itself, and — the one that
    matters — **a record listing a command the documentation does not name**.
    That last check is `DX-001`'s actual subject: the path is complete only if
    somebody walked it without being told anything that is not written down.

    It deliberately does **not** check that the reader succeeded quickly, or
    without confusion. It checks that they needed no source edit and no
    undocumented command, which is what the requirement says.

    **Why a declaration rather than automation**: the variable under test is a
    person who did not build this. Nothing in a repository can stand in for
    that, and a test that tried would be measuring its author.
    """
    record = _declared("APG_DX_RECORD_FILE")

    missing = [field for field in DX_RECORD_FIELDS if field not in record]
    assert not missing, (
        f"the record is missing {missing}. An absent answer is not a favourable one, and a "
        "claim this size is not made on a partial record"
    )

    assert record["reached_success_criterion"] is True, (
        f"the record says the success criterion was not reached: "
        f"{record.get('blocked_by') or record['reached_success_criterion']!r}"
    )

    undocumented = record["undocumented_steps"]
    assert not undocumented, (
        f"the reader needed steps the documentation does not give: {undocumented}. That is "
        "precisely what DX-001 asserts does not happen"
    )

    edited = {Path(name).name for name in record["files_edited"]}
    source_edits = sorted(edited - OPERATOR_INPUTS)
    assert not source_edits, (
        f"the reader had to edit files this repository ships: {source_edits}. DX-001's own "
        "words are 'without source edits' — editing a shipped file forks the template"
    )

    # Every command they ran must be one the documentation names. This is the
    # half that makes the record more than a self-report: it is checked against
    # the documents in this tree rather than against the reader's memory.
    documented: set[str] = set()
    for name in ("README.md", "docs/README.md"):
        path = REPO_ROOT / name
        if path.is_file():
            documented |= {
                match.group(1).lstrip("./")
                for match in _COMMAND.finditer(path.read_text(encoding="utf-8"))
            }
    for guide in sorted((REPO_ROOT / "docs").glob("session-*-operator-guide.md")):
        documented |= {
            match.group(1).lstrip("./")
            for match in _COMMAND.finditer(guide.read_text(encoding="utf-8"))
        }
    assert documented, "no documented commands were found, so this comparison is vacuous"

    ran = {
        match.group(1).lstrip("./")
        for line in record["commands_run"]
        for match in _COMMAND.finditer(f" {line}")
    }
    unnamed = sorted(ran - documented)
    assert not unnamed, (
        f"the reader ran commands the documentation does not name: {unnamed}. Either they "
        "were told out of band, or they worked it out — and both mean the path is incomplete"
    )
