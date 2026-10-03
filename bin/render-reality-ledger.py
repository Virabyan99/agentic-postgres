#!/usr/bin/env python
"""Generate the Reality Ledger page from the ledger file.

`LEDGER-001` (ADR 0247). The ledger is `docs/reality-ledger.yaml`, which a
program reads; `docs/reality-ledger.md` is what a person reads, and it is
derived here rather than kept by hand because a hand-maintained copy drifts and
the failure mode is silent -- the reason the acceptance matrix, the bounds and
the envelope are generated the same way.

The file is validated before anything is rendered, so a page is never written
from a ledger the schema refuses.

    --write   validate the ledger and regenerate the page
    --check   validate the ledger and fail if the page is missing or out of date

Exit codes (runbook §2 convention):
    0  success
    2  invalid operator input
    5  the ledger does not validate, or the page is stale or absent
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import reality_ledger  # noqa: E402

DOCUMENT = reality_ledger.PAGE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regenerate the page")
    group.add_argument("--check", action="store_true", help="verify it is current")
    args = parser.parse_args()

    try:
        ledger = reality_ledger.load()
        reality_ledger.validate(ledger)
    except reality_ledger.LedgerError as error:
        print(f"render-reality-ledger: {error}", file=sys.stderr)
        return 5

    expected = reality_ledger.render(ledger)

    if args.write:
        DOCUMENT.write_text(expected, encoding="utf-8")
        print(f"render-reality-ledger: wrote {DOCUMENT.relative_to(REPO_ROOT)}")
        return 0

    if not DOCUMENT.is_file():
        print("render-reality-ledger: the page has never been generated", file=sys.stderr)
        return 5

    if DOCUMENT.read_text(encoding="utf-8") != expected:
        print(
            "render-reality-ledger: the page is out of date; "
            "run bin/render-reality-ledger.py --write",
            file=sys.stderr,
        )
        return 5

    print("render-reality-ledger: the page is current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
