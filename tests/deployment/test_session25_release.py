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
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.deployment.test_session13_upgrade_plan import (
    candidate,  # noqa: F401 -- a fixture, used by name
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

        rendered = subprocess.run(
            [
                "./deploy.sh",
                "--project",
                str(manifest),
                "--capabilities",
                "capabilities.example.yaml",
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
    candidate: Path,  # noqa: F811 -- the imported fixture
) -> None:
    """`upgrade plan --json` prices it the class the constant's comment claims.

    This is the reading the operator's sheet makes by hand at every trip and
    writes into the plan's Done paragraph. Making it as the sweep's root is
    what turns *I read `minor` on the terminal* into a claim with a node id.

    `required <= proposed` is the second half and it is not decoration: the
    planner reports what the release PROPOSES and what the installed state
    REQUIRES, and a required class above the proposed one is exactly the
    surprise §9 stops on -- the tree believing it shipped a minor while this
    deployment would need the operator to act first.
    """
    before = deployment_state(project_key)
    proposed = proposed_class()

    result = run(
        str(UPGRADE),
        "plan",
        "--project",
        project_key,
        "--candidate",
        str(candidate),
        "--json",
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]

    payload = json.loads(result.stdout)
    order = {"patch": 0, "minor": 1, "major": 2}

    #: The payload's own names, read from `bin/upgrade.py::as_json` rather than
    #: from the plan document, which named `proposed`, `required` and
    #: `may_proceed` -- three keys this command has never emitted (D1348). What
    #: it emits is `bump` (the class the version delta PROPOSES), `requires`
    #: (the class the changes REQUIRE) and `reasons` (empty when nothing
    #: blocks). A proof written against the plan's names would have raised
    #: KeyError on the host, at the end of a fifteen-minute sweep.
    assert payload["bump"] == proposed, (
        f"`upgrade plan` prices this release {payload['bump']!r}; the constant's "
        f"comment proposes {proposed!r}. The tree and the planner disagree about what "
        "kind of release this is."
    )
    assert payload["requires"] in order, f"unknown class {payload['requires']!r}"
    assert order[payload["requires"]] <= order[proposed], (
        f"this deployment REQUIRES a {payload['requires']} upgrade and the release "
        f"proposes a {proposed}. A required class above the proposed one is the plan's "
        "§9 stop condition, not a number to write down."
    )
    assert payload["verdict"] == "ok", (
        f"the plan's verdict is {payload['verdict']!r}: " + "; ".join(payload["reasons"])
    )
    assert payload["reasons"] == [], "a plan that may proceed carries no reasons: " + "; ".join(
        payload["reasons"]
    )

    assert deployment_state(project_key) == before, "`plan` changed the deployment"
