#!/usr/bin/env python
"""Build the public site from the repository (Session 43, ADR 0283).

The pages are `site/pages/**/*.md`, rendered by `agentic_postgres.site_build`'s
Markdown subset, checked against the Reality Ledger, and laid out by
`site/templates/base.html`; the pricing page is the product's plan table and
the Ledger page its rows. CI builds this after `contract` succeeded and uploads
it to Cloudflare Pages (`.github/workflows/site.yml`); nothing built is ever
committed, so an `--out` inside the repository is refused.

    --out DIR   write the site into DIR (absent or empty)
    --check     build twice into two temporary directories and compare every byte

Exit codes (runbook §2 convention):
    0  built (or, with --check, both builds byte-equal)
    2  invalid operator input (an --out inside the repository, or not empty)
    3  a page the build refuses: the file, the line and the reason printed
    5  --check: the two builds differ
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_postgres import REPO_ROOT as PACKAGE_ROOT  # noqa: E402
from agentic_postgres import site_build  # noqa: E402


def write(out: Path) -> dict[str, bytes]:
    files = site_build.build()
    for relative, payload in files.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build-site", allow_abbrev=False)
    parser.add_argument("--out", help="an absent or empty directory outside the tree")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.check == bool(arguments.out):
        print("build-site: give exactly one of --out DIR or --check", file=sys.stderr)
        return 2
    try:
        if arguments.check:
            with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
                one, two = write(Path(first)), write(Path(second))
            if one != two:
                differing = sorted(
                    name for name in one.keys() | two.keys() if one.get(name) != two.get(name)
                )
                print(f"build-site: two builds differ in {differing}", file=sys.stderr)
                return 5
            print(
                f"build-site: {len(one)} files, two builds byte-equal, digest {site_build.digest()}"
            )
            return 0
        out = Path(arguments.out).resolve()
        if out == PACKAGE_ROOT or PACKAGE_ROOT in out.parents:
            print(f"build-site: {out} is inside the repository; nothing built is committed",
                  file=sys.stderr)  # fmt: skip
            return 2
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            print(f"build-site: {out} exists and is not an empty directory", file=sys.stderr)
            return 2
        out.mkdir(parents=True, exist_ok=True)
        files = write(out)
    except site_build.SiteError as refusal:
        print(f"build-site: refused: {refusal}", file=sys.stderr)
        return 3
    print(f"build-site: {len(files)} files into {out}, digest {site_build.digest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
