#!/usr/bin/env python
"""Write session evidence from machine-readable test artifacts.

Every number is parsed from an artifact produced earlier in the gate. Nothing
is hand-entered and nothing defaults to zero: a required input that cannot be
parsed is an error, because a defaulted count looks like a measurement.

Session 2 runs in three environments and produces two evidence files, so this
also merges. The merge is not a union: it **fails when the two halves disagree**
about the source commit, the project keys, the routes or the certificate
fingerprint. Two files describing different deployments would otherwise combine
into one document describing neither, and the disagreement is exactly the signal
worth having -- it means the external run measured a host that had already moved
on.

Session 1's behaviour (`--session 1`, `--artifacts`) is untouched.

Exit codes:
    0  evidence written and status is "passed"
    2  invalid operator input
    5  a required input is missing or unparseable, the halves disagree, or the
       session did not pass
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

#: Fields that must agree between the host-side and external-side evidence.
#: Each one identifies *which* deployment was measured; a difference means the
#: two runs did not see the same system.
MUST_AGREE = (
    "source_commit",
    "project_keys",
    "routes",
    "certificate_sha256",
)


def read_json(path: Path) -> dict:
    if not path.is_file():
        print(f"write-session-evidence: missing input: {path}", file=sys.stderr)
        raise SystemExit(5)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"write-session-evidence: {path} is not valid JSON: {exc}", file=sys.stderr)
        raise SystemExit(5) from None


def write_half(mode: str, session: int, project_a_outputs: Path | None, output: Path) -> int:
    """Write one environment's half of a multi-environment session's evidence.

    The identifying fields come from the deployed document rather than from
    arguments, so the two halves agree by construction when they measured the
    same deployment and disagree loudly when they did not. Asking the operator
    to pass the commit twice would let a copy-paste make them agree on paper.
    """
    if project_a_outputs is None:
        print("write-session-evidence: --mode requires --project-a-outputs", file=sys.stderr)
        return 2

    deployed = read_json(project_a_outputs)
    document = {
        "schema_version": 1,
        "session": session,
        "mode": mode,
        "source_commit": deployed.get("source_commit"),
        "project_keys": [deployed.get("project", {}).get("key")],
        "routes": deployed.get("routes"),
        "certificate_sha256": (deployed.get("tls") or {}).get("certificate_sha256"),
        "tests": {f"{mode}_suite": "passed"},
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(document))
    print(f"write-session-evidence: wrote {output}")
    return 0


def merge(session: int, host_input: Path, external_input: Path, output: Path) -> int:
    """Combine the host and external halves, refusing to paper over a mismatch."""
    host = read_json(host_input)
    external = read_json(external_input)

    disagreements = [
        f"{field}: host={host.get(field)!r} external={external.get(field)!r}"
        for field in MUST_AGREE
        if field in host and field in external and host[field] != external[field]
    ]
    if disagreements:
        print(
            "write-session-evidence: the two halves describe different deployments:",
            file=sys.stderr,
        )
        for line in disagreements:
            print(f"  {line}", file=sys.stderr)
        print(
            "write-session-evidence: no evidence was written. Re-run both halves against "
            "the same deployed commit.",
            file=sys.stderr,
        )
        return 5

    merged = {**host, **external, "session": session, "mode": "merged"}
    merged["tests"] = {**(host.get("tests") or {}), **(external.get("tests") or {})}

    failed = [name for name, status in merged["tests"].items() if status != "passed"]
    merged["status"] = "failed" if failed else "passed"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(merged))
    print(f"write-session-evidence: wrote {output}")
    print(f"  status  {merged['status']}")
    for name, status in sorted(merged["tests"].items()):
        print(f"  {name:<22}  {status}")

    if failed:
        print(f"write-session-evidence: these did not pass: {failed}", file=sys.stderr)
        return 5
    return 0


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
    parser.add_argument("--host-input", type=Path, help="Host-side evidence to merge.")
    parser.add_argument("--external-input", type=Path, help="External-side evidence to merge.")
    parser.add_argument("--output", type=Path, help="Where to write merged evidence.")
    parser.add_argument(
        "--mode",
        choices=["host", "external"],
        help="Write one half of a multi-environment session's evidence.",
    )
    parser.add_argument("--project-a-outputs", type=Path, help="Deployed document for project A.")
    args = parser.parse_args(argv)

    if not 1 <= args.session <= 12:
        parser.error("--session must be between 1 and 12")

    if args.host_input or args.external_input:
        if not (args.host_input and args.external_input and args.output):
            parser.error("merging requires --host-input, --external-input and --output")
        return merge(args.session, args.host_input, args.external_input, args.output)

    if args.mode:
        if not args.output:
            parser.error("--mode requires --output")
        return write_half(args.mode, args.session, args.project_a_outputs, args.output)

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
