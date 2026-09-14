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
from pathlib import Path
from typing import Any

import pytest

from agentic_postgres import REPO_ROOT, deployed_output, dx_record

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

#: The oldest outputs version whose `routes` block this proof can read.
#:
#: v16 is the version the DR kit facility first exported and the version the
#: outsider's 2026-09-08 bring-up published (ADR 0197, D1312). Below it a
#: document predates the route-status vocabulary this proof reads, so the
#: honest answer is *this release cannot read that document* rather than a
#: verdict about the host that wrote it — `dr_kit.KIT_FIRST_OUTPUTS_VERSION`
#: draws the same line for the same reason (D1141).
FIRST_READABLE_FRESH_HOST_VERSION = 16


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

    **The version is read the way the DR kit reads one, and Session 25 is why**
    (D1326, ADR 0207 §3d). This used to require the declared document to be at
    the tree's CURRENT outputs version. The artefact it exists to read is a
    document from a bring-up that happened at an older release — the outsider's
    2026-09-08 host published outputs v16 and this release renders v18 — so the
    assertion refused the only document that could ever satisfy the claim, with
    a message (*it describes an older product*) that sends an operator to
    redeploy a host that was fine.

    The obvious repair does not exist. `carry_to_current` **refuses every
    deployed document**: all sixteen single-step migrators call
    `require_kind(document, "rendered")`, which is ADR 0012 on purpose — a
    migrator that carried a deployed document forward would republish an
    observation under a version that never measured it. Measured on four real
    archived documents in rig 25f, v16 through v18.

    So this takes the shape `dr_kit.verify_deployed_document` already uses for
    exactly this problem (D1122, D1141): read by version. The current version is
    validated in full; an older one is read for what the claim is ABOUT — a
    deployed document, naming a host that is not ours, publishing ready routes —
    and a version this release cannot read at all is **reported**, not failed,
    because that is a statement about the reader.

    Goes red if: the declared document is not a deployed one, publishes no ready
    route, or is the host we already had. Reports and stays `not_run` if: the
    document is at a version this release cannot read.
    """
    fresh = _declared("APG_FRESH_HOST_OUTPUTS")

    assert fresh.get("document_kind") == "deployed", (
        f"the declared document is {fresh.get('document_kind')!r}, not a deployed one. "
        "A render proves the manifest is valid, not that a host deployed it"
    )

    version = fresh.get("schema_version")
    current = deployed_output.SCHEMA_VERSION
    assert isinstance(version, int) and not isinstance(version, bool), (
        f"the declared document's schema_version is {version!r}, not an integer. Nothing "
        "below can be read against a version that is not one"
    )
    if version > current:
        pytest.skip(
            f"the declared document is outputs version {version} and this release reads up "
            f"to {current}. Read it from a checkout at least as new as the one that wrote "
            "it; this says nothing about whether that host's deployment worked"
        )
    if version < FIRST_READABLE_FRESH_HOST_VERSION:
        pytest.skip(
            f"the declared document is outputs version {version}, below "
            f"{FIRST_READABLE_FRESH_HOST_VERSION} — older than any document this release can "
            "read the routes of. DEP-001 stays not_run with the version named, rather than "
            "failing a deployment nobody has shown to be broken"
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


@pytest.mark.live_host
@pytest.mark.requires_environment("APG_DX_RECORD_FILE")
def test_a_developer_who_did_not_build_this_completed_the_documented_path() -> None:
    """`DX-001`. The one claim in this repository that a test cannot make alone.

    **The record is a declaration and this refuses a false one.** An incomplete
    record, a record that contradicts itself, and -- the one that matters -- a
    record listing a command the documentation does not name. That last check is
    `DX-001`'s actual subject: the path is complete only if somebody walked it
    without being told anything that is not written down.

    It deliberately does **not** check that the reader succeeded quickly, or
    without confusion. It checks that they needed no source edit and no
    undocumented command, which is what the requirement says.

    **Why a declaration rather than automation**: the variable under test is
    somebody who did not build this. Nothing in a repository can stand in for
    that, and a test that tried would be measuring its author.

    **Every reading here is `dx_record`'s, and that is Session 25's repair**
    (ADR 0207 §3). The checks used to live in this module, comparing edited
    files by BASENAME against five operator inputs and resolving commands no
    further than `bin/apg.sh`. They were written in Session 12, six sessions
    before an adopter had a directory of their own, and **no record was ever
    declared, so they had never run**. Rig 25d ran them for the first time
    against a walk that followed README exactly: seven false source edits, and
    `bin/apg.sh no-such-verb` passing while `bin/dev.sh up` was refused. The
    same four functions now answer for the walker, through
    `bin/apg.sh dx-record check`, so nobody is marked by a rubric they could
    not run.

    Goes red if: the walker edited a file this repository ships, ran a command
    no document names, read a document that has moved since, recorded a
    `followed_by` that does not say what their context held, or did not reach
    the success criterion.
    """
    path = Path(os.environ["APG_DX_RECORD_FILE"])
    try:
        record = dx_record.load(path)
    except (dx_record.RecordUnreadable, dx_record.RecordIncomplete) as problem:
        pytest.fail(str(problem))

    shape = dx_record.shape_problems(record)
    assert not shape, (
        f"the record's shape is wrong, so every reading below would be answering a "
        f"different question: {shape}"
    )

    absent = dx_record.absent_documents(record, REPO_ROOT)
    assert not absent, (
        f"the record names documents this checkout does not have: {absent}. That is a "
        "statement about the tree this sweep is reading, not about the walk"
    )

    assert record.reached_success_criterion is True, (
        f"the record says the success criterion was not reached: "
        f"{record.document.get('blocked_by') or record.reached_success_criterion!r}"
    )

    assert not record.undocumented_steps, (
        f"the reader needed steps the documentation does not give: "
        f"{record.undocumented_steps}. That is precisely what DX-001 asserts does not happen"
    )

    source_edits = dx_record.source_edits(record)
    assert not source_edits, (
        f"the reader had to edit files this repository ships: {source_edits}. DX-001's own "
        "words are 'without source edits' — editing a shipped file forks the template. "
        f"Files under projects/{record.project_slug}/ are the walker's own and are not "
        "counted (ADR 0198, ADR 0207)"
    )

    documented = dx_record.documented_commands(REPO_ROOT)
    assert documented, "no documented commands were found, so this comparison is vacuous"
    unnamed = dx_record.unnamed_commands(record, documented)
    assert not unnamed, (
        f"the reader ran commands the documentation does not name: {unnamed}. Either they "
        "were told out of band, or they worked it out — and both mean the path is incomplete"
    )

    stale = dx_record.stale_documents(record, REPO_ROOT)
    assert not stale, (
        f"the documentation moved after the walk: {stale}. A walk is a measurement of a "
        "document at a commit; walk again, or record why this reading still stands"
    )

    followed_by = dx_record.followed_by_problems(record)
    assert not followed_by, (
        f"the record does not say whose walk this was, in the terms ADR 0207 admits: "
        f"{followed_by}. A claim closed by its author's hands leaves the next reader unable "
        "to tell a proved guarantee from a plausible one (D478)"
    )
