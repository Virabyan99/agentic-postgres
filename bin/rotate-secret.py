#!/usr/bin/env python3
"""What rotating a declared secret would do. Reads everything, changes nothing.

**No verb here writes a value, at the provider or anywhere else** -- D249's rule,
which `rotate-signing-key.sh` already keeps: setting a secret is done by hand at
the provider and picked up by the next deploy. What this owns is the answer to
*"if I replace this, what happens"*, and the useful part is the refusals.

Two secrets in the contract cannot be rotated by replacing them, and both look
exactly like the seventeen that can: same shape, same consumers, same plane. A
plan that printed their file paths and their services would be describing, in
detail, a rotation that does not happen -- which is D56, and the reason the
lifecycle vocabulary was written down five sessions ago.

Exit codes (runbook section 2 convention):
  0  the plan was produced
  2  invalid operator input
  3  missing local prerequisite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import CURRENT_SESSION, REPO_ROOT, rotation
from agentic_postgres.secrets_contract import load_secret_contract

EXIT_INPUT = 2
EXIT_PREREQUISITE = 3

CONTRACT = REPO_ROOT / "secrets.required.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rotate-secret",
        description="What rotating a declared secret would do. Changes nothing.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--secret-name",
        metavar="NAME",
        help="plan one secret by name; omit for every secret this session issues",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=CURRENT_SESSION,
        metavar="N",
        help=f"the session whose secrets to plan (default {CURRENT_SESSION})",
    )
    arguments = parser.parse_args(argv)

    if not CONTRACT.is_file():
        print(f"rotate-secret: no contract at {CONTRACT}", file=sys.stderr)
        return EXIT_PREREQUISITE

    contract = load_secret_contract(CONTRACT)
    verdicts = rotation.plan_all(contract, arguments.session)

    if arguments.secret_name:
        verdicts = [v for v in verdicts if v.name == arguments.secret_name]
        if not verdicts:
            declared = {s["name"] for s in contract["secrets"]}
            if arguments.secret_name in declared:
                print(
                    f"rotate-secret: {arguments.secret_name} is declared but is not issued at "
                    f"session {arguments.session}",
                    file=sys.stderr,
                )
            else:
                print(f"rotate-secret: no secret named {arguments.secret_name}", file=sys.stderr)
            return EXIT_INPUT

    for verdict in verdicts:
        print(verdict.render())
        print()

    rotatable = [v for v in verdicts if v.rotates]
    refused = [v for v in verdicts if not v.rotates]
    supplied = [v for v in rotatable if v.operator_supplied]

    print(f"{len(rotatable)} rotate by replacement, {len(refused)} do not.")
    if supplied:
        print(
            f"{len(supplied)} of those take a value from a third party and cannot be "
            "generated here: " + ", ".join(v.name for v in supplied)
        )
    print()
    print(rotation.MUST_REFRESH_IS_NOT_YET_A_CONTROL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
