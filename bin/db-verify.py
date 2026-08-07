#!/usr/bin/env python3
"""Verify a generated SQL artifact against the manifest that produced it.

Invoked by ``bin/db.sh`` before anything is executed. Separate from the shell
script because a digest comparison written in bash is a string comparison
someone eventually relaxes to a prefix.

The manifest lives beside the artifact and records the digest at generation
time. This exists so that "the file the renderer wrote" and "the file about to
be executed as superuser" are demonstrably the same bytes -- an artifact edited
after rendering is refused, which is the only thing standing between an
allowlisted name and arbitrary SQL.
"""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--artifact", required=True)
    arguments = parser.parse_args()

    artifact = Path(arguments.artifact)
    manifest = artifact.parent / "rendered-manifest.json"

    if not manifest.is_file():
        print(f"db-verify: no rendered manifest beside {artifact.name}", file=sys.stderr)
        return 1

    recorded = json.loads(manifest.read_text(encoding="utf-8")).get("artifacts", {})
    expected = recorded.get(artifact.name)
    if expected is None:
        # An artifact the manifest never named is not "unverified", it is
        # unaccounted for -- the renderer did not produce it.
        print(f"db-verify: {artifact.name} is not named by the rendered manifest", file=sys.stderr)
        return 1

    actual = sha256(artifact.read_bytes()).hexdigest()
    if actual != expected:
        print(
            f"db-verify: {artifact.name} does not match the manifest\n"
            f"  manifest {expected}\n  actual   {actual}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
