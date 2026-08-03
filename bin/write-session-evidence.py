#!/usr/bin/env python
"""Write session evidence from machine-readable test artifacts.

Every number is parsed from an artifact produced earlier in the gate. Nothing
is hand-entered and nothing defaults to zero: a required input that cannot be
parsed is an error, because a defaulted count looks like a measurement.

Exit codes:
    0  evidence written and status is "passed"
    2  invalid operator input
    5  a required input is missing or unparseable, or the session did not pass
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import evidence as evidence_module  # noqa: E402
from agentic_postgres.naming import canonical_json  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bin/write-session-evidence.py",
        description="Generate evidence/session-NN.json from gate artifacts.",
    )
    parser.add_argument("--session", type=int, required=True, help="Session number, 1-12.")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=None,
        help="Directory holding contract-tests.xml and p0-collection.txt.",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.session <= 12:
        parser.error("--session must be between 1 and 12")

    artifacts = args.artifacts or (REPO_ROOT / ".generated" / f"session-{args.session:02d}")

    try:
        document = evidence_module.build(args.session, artifacts)
    except evidence_module.EvidenceError as exc:
        print(f"write-session-evidence: {exc}", file=sys.stderr)
        print("write-session-evidence: no evidence file was written.", file=sys.stderr)
        return 5

    destination = REPO_ROOT / "evidence" / f"session-{args.session:02d}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json(document))

    counts = document["contract_tests"]
    print(f"write-session-evidence: wrote {destination.relative_to(REPO_ROOT)}")
    print(f"  status                  {document['status']}")
    print(f"  source commit           {document['source_commit'][:12]}")
    print(
        f"  contract tests          {counts['passed']} passed, "
        f"{counts['failed']} failed, {counts['errors']} errors"
    )
    print(f"  P0 collected            {document['p0_tests_collected']}")
    print(f"  P0 future placeholders  {document['p0_tests_future']}")
    print(f"  rendered projects       {', '.join(document['rendered_projects'])}")
    print(f"  identity collisions     {document['project_scoped_collision_count']}")
    print(f"  floating image refs     {document['floating_image_references']}")

    if document["status"] != "passed":
        print(
            "write-session-evidence: the session did not pass; evidence records the failure.",
            file=sys.stderr,
        )
        return 5

    # Round-trip so a malformed write is caught here, not by a later consumer.
    json.loads(destination.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
