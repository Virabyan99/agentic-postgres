#!/usr/bin/env python
"""Generate the evaluation report from the committed capability contract.

The report is what a person reads to find out what the evaluation harness asks
of this deployment's agent surface: every case derived from the contract, one
adversarial case per frozen field, and every hand-written case beside it,
counted separately (ADR 0184, D868). It is derived from
``contracts/snapshots/mcp/mcp-capabilities.canonical.json`` and
``tests/evaluation-cases.yaml`` for the reason ``render-mcp-catalog.py`` derives
the catalog from the contract: a hand-maintained inventory drifts, and the
failure mode is silent -- a capability listed as covered whose cases were
written against a version it no longer declares.

**The render REFUSES when a capability has no cases**, with exit 5. That is
the gate's and CI's half of `EVAL-HARNESS-001`: the offline gate runs
``--check``, so a capability added without its cases fails the gate rather than
appearing in the report as a row of zeros.

**A project's report** (ADR 0201, ``EVAL-HARNESS-002``). ``--project FILE``
names a project manifest that declares ``mcp.capabilities``, and the report
rendered is ``projects/<slug>/contracts/evaluation-report.md``, from the JOINT
contract that project's lock is compiled from -- so the digest it carries is
the one that project's deployed document publishes. Its written cases are the
release's, less those for capabilities the project disabled, plus the
project's own at ``projects/<slug>/evaluation-cases.yaml`` if that file exists.
The same refusal applies: a project capability without cases exits 5.

The report carries no OUTCOME. An outcome is what the evaluation observes when
it runs -- ``tests/contract/test_evaluation_harness.py`` -- and a document
asserting one would be a proof result committed as prose. What it carries is
what was asked, and the digest of the contract it was asked of, which is the
number the deployed document publishes as ``capability_contract_sha256`` and
the live half compares.

``--check`` never writes. The Session 1 gate demands a clean tree before it
runs, so a generator that self-healed mid-gate would dirty the tree it just
required be clean.

Exit codes:
    0  success
    2  invalid operator input
    5  generated documentation has drifted, or a capability has no cases
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, capability_manifest, config, evaluation_harness

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
REPORT = REPO_ROOT / "docs" / "evaluation-report.md"
RELEASE_CAPABILITIES = REPO_ROOT / "capabilities.example.yaml"
PROJECT_CASES_NAME = "evaluation-cases.yaml"

BEGIN = "<!-- BEGIN GENERATED: evaluation-report -->"
END = "<!-- END GENERATED: evaluation-report -->"

#: What a project's report file holds around its generated block when this
#: command creates it. Short on purpose: the release's report explains what a
#: case is, and a project's is an inventory beside its contract.
PROJECT_REPORT_HEAD = """# The evaluation report for this project

What the evaluation harness asks of THIS project's agent surface -- the
release's capabilities less the ones this project disables, plus its own --
and nothing about what it answered. The digest below is the one this project's
deployed document publishes as `capability_contract_sha256`.

**The block below is generated** by `bin/render-evaluation-report.py --project
<manifest>` from the joint contract and the written cases (the release's under
`tests/evaluation-cases.yaml`, this project's under `evaluation-cases.yaml`
beside its manifest, if any). Regenerate rather than edit; `--check` catches a
drift (ADR 0201, `EVAL-HARNESS-002`).

"""


def shown(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def compose(existing: str, generated: str, report: Path) -> str:
    if BEGIN not in existing or END not in existing:
        raise SystemExit(f"{report} has no generated block. It must contain {BEGIN} and {END}.")
    head = existing[: existing.index(BEGIN) + len(BEGIN)]
    tail = existing[existing.index(END) :]
    return f"{head}\n\n{generated}\n\n{tail}"


@dataclass(frozen=True)
class Target:
    """One report: which contract, which case files, which file."""

    report: Path
    contract: dict[str, Any]
    #: The case files, in the order they are read; the sources named in a
    #: drift message.
    cases: tuple[Path, ...]
    #: The release capabilities a project disabled; empty for the release.
    disabled: frozenset[str]


def release_target() -> Target:
    return Target(
        report=REPORT,
        contract=json.loads(CONTRACT.read_text(encoding="utf-8")),
        cases=(evaluation_harness.WRITTEN_CASES_PATH,),
        disabled=frozenset(),
    )


def project_target(project_path: Path) -> Target:
    manifest = config.load_project_manifest(project_path)
    inputs = capability_manifest.project_inputs(manifest)
    if inputs is None:
        raise config.ManifestError(
            f"{project_path} declares no mcp.capabilities, so its report is the release's: "
            "run without --project"
        )
    release = config.load_capabilities_manifest(RELEASE_CAPABILITIES)
    joint = capability_manifest.compile_joint_contract(release, inputs)
    own_cases = inputs.root / PROJECT_CASES_NAME
    return Target(
        report=capability_manifest.project_report_path(inputs.root),
        contract=joint,
        cases=(evaluation_harness.WRITTEN_CASES_PATH,)
        + ((own_cases,) if own_cases.is_file() else ()),
        disabled=frozenset(capability_manifest.disabled_release_capabilities(inputs.capabilities)),
    )


def render(target: Target) -> str:
    derived = evaluation_harness.derive_cases(target.contract)
    written: tuple[evaluation_harness.Case, ...] = ()
    for path in target.cases:
        written += evaluation_harness.load_written_cases(
            target.contract, path, disabled=target.disabled
        )
    return evaluation_harness.render_report(target.contract, derived, written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the report")
    group.add_argument("--check", action="store_true", help="report drift; never write")
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="a project manifest naming mcp.capabilities; renders that project's report "
        "beside its contract, from the joint contract its lock is compiled from (ADR 0201)",
    )
    arguments = parser.parse_args()

    try:
        target = (
            release_target() if arguments.project is None else project_target(arguments.project)
        )
        generated = render(target)
    except evaluation_harness.HarnessError as error:
        print(f"render-evaluation-report: {error}", file=sys.stderr)
        return 5
    except config.ManifestError as error:
        print(f"render-evaluation-report: {error}", file=sys.stderr)
        return 2

    report = target.report
    if report.is_file():
        existing = report.read_text(encoding="utf-8")
    elif arguments.project is not None:
        existing = f"{PROJECT_REPORT_HEAD}{BEGIN}\n{END}\n"
    else:
        raise SystemExit(f"{report} does not exist")
    wanted = compose(existing, generated, report)
    sources = " or ".join(shown(path) for path in target.cases)

    if arguments.check:
        if not report.is_file():
            print(
                f"render-evaluation-report: {shown(report)} does not exist. Run "
                f"bin/render-evaluation-report.py --write --project {arguments.project}.",
                file=sys.stderr,
            )
            return 5
        if wanted != existing:
            print(
                f"render-evaluation-report: {shown(report)} has drifted from its contract or "
                f"{sources}. Run bin/render-evaluation-report.py --write"
                + (f" --project {arguments.project}." if arguments.project else "."),
                file=sys.stderr,
            )
            return 5
        print(f"render-evaluation-report: {shown(report)} is current")
        return 0

    if not report.is_file() or wanted != existing:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(wanted, encoding="utf-8")
        print(f"render-evaluation-report: updated {shown(report)}")
    else:
        print(f"render-evaluation-report: {shown(report)} was already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
