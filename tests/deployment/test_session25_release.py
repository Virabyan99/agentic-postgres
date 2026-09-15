"""`REL-STAGE-001`'s live half — the Stage 3 release, on the deployment.

**One claim, and a checkout cannot answer any of it.**

The tree says what release it is: `VERSION` holds `1.6.0`, `CURRENT_SESSION`
holds 25, and the paragraph above that constant prices the upgrade a MINOR.
`tests/contract/test_release_contract.py` holds those three to each other. It
cannot hold any of them to a deployment, because whether a running project is
*at* the release the tree names is a fact about the running project, and
whether the upgrade to it is a minor is a fact about what the operator would
have to supply — which only the deployment's own installed document knows.

**Both projects, not one.** Alpha declares nothing of its own and beta carries
a migration set and a capability manifest, and they have come apart before: at
Session 24's trip beta was refused while alpha deployed (D1288), and a release
claim measured on alpha alone would have said the release was deployed. So the
proof reads both documents and runs `verify` for both keys, and names the one
that disagrees.

**The candidate is rendered by `test_session13_upgrade_plan.py`'s mechanism,
not by a second one.** That fixture renders the deployment's own installed
manifest with `--render-only`, into `.generated/<key>`, and removes only what
it created. Copying it would be a second authority on how a candidate is made
(ADR 0002) and would also duplicate D1164's named suspect: the fixture is the
one that leaves `.generated/<key>` root-owned when the sweep runs as root, and
the owner is recorded here before and after so a reading exists rather than a
suspicion.

**The class this proof reads is not chosen here.** It is parsed out of the
constant's own comment, by the same reader the offline half uses, so the
number `upgrade plan` is compared against is the number the release wrote
down. A `major` is §9's stop condition, and a stop condition compared against
a literal a test author typed is a stop condition about the test author.

**Gated on three declarations.** `APG_LIVE_HOST` and the two project outputs
are all in `tests/conftest.py::ENVIRONMENT_VARIABLES`; nothing here reads a
credential, and nothing here mutates the deployment (D1114: every reading is
made by running the product's own command).

**Marked, and the marks are load-bearing** (D1240).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.deployment.test_session13_upgrade_plan import (
    deployment_state,
    project_key,  # noqa: F401 -- a fixture, used by name
    run,
)

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, deployed_output, template_version

pytestmark = [
    pytest.mark.p0,
    pytest.mark.deployment,
    pytest.mark.live_host,
    pytest.mark.requires_environment(
        "APG_LIVE_HOST", "APG_PROJECT_A_OUTPUTS", "APG_PROJECT_B_OUTPUTS"
    ),
]

UPGRADE = REPO_ROOT / "bin" / "upgrade.sh"

#: The capability manifest an operator actually deploys with. **Not
#: `capabilities.example.yaml`** (D1371): that file is the REVIEWED SET the
#: release compiles its contract from, and it is not what any deployment is
#: rendered with. On this host the operator's own manifest enables nothing at
#: all, which is correct and is D930 -- the host's manifest does not decide the
#: deployed lock, the committed canonical contract does. A candidate rendered
#: from the example therefore differs from the installed document in every
#: `capabilities.enabled` leaf, and `upgrade verify` says so truthfully.
OPERATOR_CAPABILITIES = REPO_ROOT / "capabilities.yaml"


@pytest.fixture
def release_candidate(project_key: str) -> Iterator[Path]:  # noqa: F811
    """What this checkout renders for the deployed project, from ITS manifests.

    Session 13's `candidate` fixture renders from `capabilities.example.yaml`
    and that is right for what it proves -- a plan is produced and the
    deployment is unchanged -- because those readings do not depend on the
    capability manifest agreeing. Everything here does, so this renders from
    the two manifests the deployment records: the installed project manifest,
    and the operator's own capability manifest beside the checkout.

    `capabilities.yaml` is a gitignored operator input. On a host it exists
    because the deploy required it; if it does not, this fails saying so rather
    than falling back to the example, because the fallback is the defect
    (D1371).

    It deletes only what it published, for the reason Session 13's does: the
    gate compares every rendered project under `.generated/` for identity
    collisions, so a proof that renders a real project beside the fixtures must
    take its directory away again.
    """
    manifest = deployed_output.PROJECT_STATE_ROOT / project_key / "manifest.yaml"
    if not manifest.is_file():
        pytest.fail(f"no installed manifest at {manifest}")
    if not OPERATOR_CAPABILITIES.is_file():
        pytest.fail(
            f"no operator capability manifest at {OPERATOR_CAPABILITIES}. This proof renders "
            "the candidate from the manifests the deployment was rendered from; "
            "capabilities.example.yaml is the reviewed set and is NOT one of them (D1371)."
        )

    published = REPO_ROOT / ".generated" / project_key
    ours = not published.exists()

    result = subprocess.run(
        [
            "./deploy.sh",
            "--project",
            str(manifest),
            "--capabilities",
            str(OPERATOR_CAPABILITIES),
            "--render-only",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    rendered = published / "outputs.json"
    assert rendered.is_file(), f"--render-only wrote no document at {rendered}"
    try:
        yield rendered
    finally:
        if ours:
            shutil.rmtree(published, ignore_errors=True)


INIT = REPO_ROOT / "src" / "agentic_postgres" / "__init__.py"


def proposed_class() -> str:
    """The ADR 0162 class the release's own comment proposes.

    Read from the source rather than typed here, for the reason the module
    docstring gives: the offline half asserts the comment says this, and this
    half asserts the deployment agrees with what it says. Two proofs reading
    one statement is the point; two proofs each carrying their own copy of it
    is how a release gets priced twice.
    """
    head, marker, _ = INIT.read_text(encoding="utf-8").partition("CURRENT_SESSION = ")
    assert marker, "CURRENT_SESSION is not assigned in __init__.py"
    lines = [line for line in head.splitlines() if line.startswith("#:")]
    priced = re.findall(r"ADR 0162 prices it (?:a |an )?([A-Za-z]+)", "\n".join(lines))
    assert priced, "the constant's comment prices no release"
    return priced[-1].lower()


def _owner(path: Path) -> str:
    """`uid:gid` of a path, or why it could not be read (ADR 0195).

    D1164's reading. `--render-only` run by the sweep's root leaves
    `.generated/<key>` root-owned, and CLAUDE.md's note is that only a real
    root login, a `sudo pytest` or a root `--render-only` does it. A sweep IS a
    `sudo pytest`, so this records the owner rather than asserting one: the
    finding, if there is one, is a number in the Done paragraph and an
    `chown -R op:op .generated` on the sheet, not a red proof about a staging
    directory.
    """
    try:
        stat = path.stat()
    except OSError as error:
        return f"unreadable:{error.errno}"
    return f"{stat.st_uid}:{stat.st_gid}"


def _both_keys(project_a: dict[str, Any], project_b: dict[str, Any]) -> list[tuple[str, dict]]:
    keys: list[tuple[str, dict]] = []
    for document in (project_a, project_b):
        key = document.get("project", {}).get("key")
        assert key, "a declared deployed document names no project key"
        keys.append((str(key), document))
    assert keys[0][0] != keys[1][0], (
        f"both declarations name the same project {keys[0][0]!r}; "
        "APG_PROJECT_A_OUTPUTS and APG_PROJECT_B_OUTPUTS point at one document"
    )
    return keys


# ---------------------------------------------------------------------------
# REL-STAGE-001 — both projects run this release, and verify against it
# ---------------------------------------------------------------------------


def test_both_projects_run_this_release_and_verify_against_it(
    as_root: None, project_a: dict[str, Any], project_b: dict[str, Any]
) -> None:
    """Each deployed document is at this release, and `verify` agrees.

    The document half and the command half are both here deliberately. A
    document carries `template_version` because a render wrote it; `verify`
    goes further and says the installed rendered document and the candidate
    this checkout produces are compatible under ADR 0162's rules. A release
    that had been half-deployed -- the document stamped, the artefacts not --
    passes the first and fails the second.
    """
    release = template_version()
    disagreed: list[str] = []

    for key, document in _both_keys(project_a, project_b):
        installed = document.get("template_version")
        if installed != release:
            disagreed.append(
                f"{key}: the deployed document says template_version {installed!r}, "
                f"and the tree is {release!r}"
            )
        through = document.get("deployed_through_session")
        if through != CURRENT_SESSION:
            disagreed.append(
                f"{key}: the deployed document says deployed_through_session "
                f"{through!r}, and CURRENT_SESSION is {CURRENT_SESSION}"
            )

    assert not disagreed, "the deployment is not at the release this tree names:\n  " + "\n  ".join(
        disagreed
    )

    for key, _ in _both_keys(project_a, project_b):
        manifest = deployed_output.PROJECT_STATE_ROOT / key / "manifest.yaml"
        assert manifest.is_file(), f"no installed manifest at {manifest}"

        published = REPO_ROOT / ".generated" / key
        ours = not published.exists()
        before_owner = _owner(published)

        # **The operator's manifest, not the example** (D1371). See
        # `OPERATOR_CAPABILITIES`: rendering from the reviewed set produces a
        # document with eight enabled capabilities where the deployment's has
        # none, and `verify` reports eight differing leaves -- truthfully, about
        # a comparison that should never have been made.
        assert OPERATOR_CAPABILITIES.is_file(), (
            f"no operator capability manifest at {OPERATOR_CAPABILITIES}; this proof "
            "renders the candidate from the manifests the deployment was rendered from"
        )
        rendered = subprocess.run(
            [
                "./deploy.sh",
                "--project",
                str(manifest),
                "--capabilities",
                str(OPERATOR_CAPABILITIES),
                "--render-only",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rendered.returncode == 0, (
            f"{key}: --render-only exited {rendered.returncode}\n"
            + rendered.stdout[-3000:]
            + rendered.stderr[-3000:]
        )
        after_owner = _owner(published)
        print(f"D1164 reading: .generated/{key} owner before={before_owner} after={after_owner}")

        try:
            before = deployment_state(key)
            result = run(
                str(UPGRADE),
                "verify",
                "--project",
                key,
                "--candidate",
                str(published / "outputs.json"),
            )
            assert result.returncode == 0, (
                f"{key}: `upgrade verify` exited {result.returncode} against the release "
                f"this checkout renders\n" + result.stdout[-3000:] + result.stderr[-3000:]
            )
            assert deployment_state(key) == before, f"{key}: `verify` changed the deployment"
        finally:
            if ours:
                import shutil

                shutil.rmtree(published, ignore_errors=True)


# ---------------------------------------------------------------------------
# REL-STAGE-001 — the plan prices the release as the tree proposes
# ---------------------------------------------------------------------------


def test_the_plan_priced_this_release_as_the_class_it_proposes(
    as_root: None,
    project_key: str,  # noqa: F811 -- the imported fixture
    release_candidate: Path,
) -> None:
    """After the deploy: the deployment IS what this checkout renders.

    **This proof used to assert `verdict == "ok"` and it could never pass**
    (D1372). `plan` prices a candidate against what is installed, and the sweep
    runs AFTER the deploy -- so the installed version is the candidate, the
    planner answers *the candidate is not ahead of what is installed*, and
    blocks. Correctly. Written in Run 5, first executed on the host on
    2026-09-15, red on its first execution: §7's second question, which asks
    whether a proof has run at all in the environment it is about.

    **The class reading it wanted is inherently pre-deploy.** `bump: minor`
    exists only while the installed version is behind the candidate, which is
    true at the operator's `upgrade plan` step and false forever after. That
    reading stays what it always was -- an operator observation, made before the
    deploy and recorded in the run's Done -- and this proof measures what a
    sweep can actually measure.

    **What it measures instead is stronger than the class.** `differences == []`
    says the installed rendered document and the one this checkout renders agree
    at every leaf; `operator_digests_moved == []` says the candidate was rendered
    from the manifests the deployment was rendered from, which is the whole of
    D1371. A release stamped but half-applied fails both.
    """
    before = deployment_state(project_key)
    proposed = proposed_class()

    result = run(
        str(UPGRADE),
        "plan",
        "--project",
        project_key,
        "--candidate",
        str(release_candidate),
        "--json",
    )
    # NOT `returncode == 0`: a plan that reports nothing left to do exits
    # non-zero by design, and that is the expected answer after a deploy.
    payload = json.loads(result.stdout)
    order = {"patch": 0, "minor": 1, "major": 2}

    #: The payload's own names, read from `bin/upgrade.py::as_json` rather than
    #: from the plan document, which named `proposed`, `required` and
    #: `may_proceed` -- three keys this command has never emitted (D1348).
    release = template_version()
    assert payload["installed_version"] == release, (
        f"the deployment reports installed {payload['installed_version']!r} and this tree "
        f"is {release!r}; the deploy did not land, or landed something else"
    )
    assert payload["candidate_version"] == release, (
        f"the candidate rendered {payload['candidate_version']!r}, not {release!r}"
    )

    #: **The heart of it, and D1371's whole subject.** A candidate rendered from
    #: a capability manifest the deployment was not rendered from moves this
    #: list, and every reading below becomes a comparison between two different
    #: operators' intentions rather than between a release and its deployment.
    assert payload["operator_digests_moved"] == [], (
        "the candidate was rendered from different operator inputs than the "
        f"deployment: {payload['operator_digests_moved']}. Render it from the manifests "
        "this deployment records, never from capabilities.example.yaml (D1371)."
    )
    assert payload["differences"] == [], (
        "the installed rendered document and the one this checkout renders differ at "
        f"{len(payload['differences'])} leaf/leaves, so the release is not fully applied: "
        + "; ".join(
            f"{d['path']}: {d['installed']!r} -> {d['candidate']!r}"
            for d in payload["differences"][:8]
        )
    )

    #: `requires <= proposed` still holds and is still worth asserting: a
    #: deployment requiring MORE than the release proposes is §9's stop, and it
    #: is a statement about the installed state rather than about the delta.
    assert payload["requires"] in order, f"unknown class {payload['requires']!r}"
    assert order[payload["requires"]] <= order[proposed], (
        f"this deployment REQUIRES a {payload['requires']} upgrade and the release "
        f"proposes a {proposed}. A required class above the proposed one is the plan's "
        "§9 stop condition, not a number to write down."
    )

    #: The post-deploy verdict, and the reason it carries. `blocked` here means
    #: *there is nothing left to do*, which is what a finished deploy looks like
    #: to a planner -- not a fault. A `blocked` for any OTHER reason would be.
    assert payload["verdict"] == "blocked", (
        f"after a deploy the planner should have nothing left to propose, and it says "
        f"{payload['verdict']!r}: " + "; ".join(payload["reasons"])
    )
    assert payload["reasons"], "a blocked plan must say why"
    assert all("not ahead" in reason for reason in payload["reasons"]), (
        "the plan is blocked for a reason other than the release already being "
        "installed, which is a finding rather than a finished deploy: "
        + "; ".join(payload["reasons"])
    )

    assert deployment_state(project_key) == before, "`plan` changed the deployment"
