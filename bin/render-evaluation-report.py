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
    5  generated documentation has drifted, or a capability has no cases
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import REPO_ROOT, evaluation_harness

CONTRACT = REPO_ROOT / "contracts" / "snapshots" / "mcp" / "mcp-capabilities.canonical.json"
REPORT = REPO_ROOT / "docs" / "evaluation-report.md"

BEGIN = "<!-- BEGIN GENERATED: evaluation-report -->"
END = "<!-- END GENERATED: evaluation-report -->"


def shown(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def compose(existing: str, generated: str) -> str:
    if BEGIN not in existing or END not in existing:
        raise SystemExit(f"{REPORT} has no generated block. It must contain {BEGIN} and {END}.")
    head = existing[: existing.index(BEGIN) + len(BEGIN)]
    tail = existing[existing.index(END) :]
    return f"{head}\n\n{generated}\n\n{tail}"


def render() -> str:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    derived = evaluation_harness.derive_cases(contract)
    written = evaluation_harness.load_written_cases(contract)
    return evaluation_harness.render_report(contract, derived, written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the report")
    group.add_argument("--check", action="store_true", help="report drift; never write")
    arguments = parser.parse_args()

    try:
        generated = render()
    except evaluation_harness.HarnessError as error:
        print(f"render-evaluation-report: {error}", file=sys.stderr)
        return 5
    existing = REPORT.read_text(encoding="utf-8")
    wanted = compose(existing, generated)

    if arguments.check:
        if wanted != existing:
            print(
                f"render-evaluation-report: {shown(REPORT)} has drifted from {shown(CONTRACT)} "
                f"or {shown(evaluation_harness.WRITTEN_CASES_PATH)}. "
                "Run bin/render-evaluation-report.py --write.",
                file=sys.stderr,
            )
            return 5
        print(f"render-evaluation-report: {shown(REPORT)} is current")
        return 0

    if wanted != existing:
        REPORT.write_text(wanted, encoding="utf-8")
        print(f"render-evaluation-report: updated {shown(REPORT)}")
    else:
        print(f"render-evaluation-report: {shown(REPORT)} was already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
